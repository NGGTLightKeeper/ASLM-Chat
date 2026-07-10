# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Cross-browser profile import: cookie decryption, store layer, config gating, transport merge.

Hermetic — never reads the machine's real browser profiles. Chromium value decryption is proven
with a synthetic AES-GCM v10 blob under a known key (the DPAPI key-unwrap step is Windows-only
and is exercised separately by discovery, not here); Firefox with a synthetic plaintext DB.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from core.engines.models import EngineRequest
from core.fetch.browser import profile_import as PI
from core.fetch.browser.identity_store import IdentityStore
from core.fetch.browser.profile_import import DomainFilter, ImportedCookie


# ── Config gating ─────────────────────────────────────────────────────────────────────

def test_profile_import_disabled_by_default():
    from core.config.settings import load_search_config

    cfg = load_search_config()
    assert cfg.profile_import.enabled is False
    # Cross-browser set present by default so enabling it needs no extra config.
    assert set(cfg.profile_import.browsers) == {"chrome", "edge", "brave", "firefox"}


def test_config_string_list_drops_unknown_browser(tmp_path):
    import json
    from core.config.settings import load_search_config

    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({"profile_import": {"browsers": ["chrome", "netscape", "firefox"]}}))
    cfg = load_search_config(path=path)
    assert cfg.profile_import.browsers == ["chrome", "firefox"]  # "netscape" dropped


# ── Chromium value decryption (AES-GCM v10) ───────────────────────────────────────────

def _aesgcm_v10(key: bytes, plaintext: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    return b"v10" + nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def test_decrypt_chromium_v10_roundtrip():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = AESGCM.generate_key(bit_length=256)
    blob = _aesgcm_v10(key, b"session-token-123")
    plain, ok = PI._decrypt_chromium_value(blob, key)
    assert ok is True
    assert plain == "session-token-123"


def test_decrypt_chromium_v10_wrong_key_is_skipped_not_fabricated():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    blob = _aesgcm_v10(AESGCM.generate_key(bit_length=256), b"secret")
    plain, ok = PI._decrypt_chromium_value(blob, AESGCM.generate_key(bit_length=256))
    assert ok is False and plain == ""  # bad tag → skipped, never a garbage value


def test_decrypt_chromium_v20_app_bound_is_not_decryptable():
    # App-Bound Encryption is sealed to the browser process; we must not pretend to read it.
    plain, ok = PI._decrypt_chromium_value(b"v20" + os.urandom(40), os.urandom(32))
    assert ok is False and plain == ""


# ── Synthetic cookie DBs ──────────────────────────────────────────────────────────────

def _make_chromium_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE cookies (host_key TEXT, name TEXT, encrypted_value BLOB, value TEXT, "
        "path TEXT, expires_utc INTEGER, is_secure INTEGER, is_httponly INTEGER)"
    )
    conn.executemany(
        "INSERT INTO cookies (host_key, name, encrypted_value, value, path, expires_utc, "
        "is_secure, is_httponly) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def _make_firefox_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE moz_cookies (host TEXT, name TEXT, value TEXT, path TEXT, "
        "expiry INTEGER, isSecure INTEGER, isHttpOnly INTEGER)"
    )
    conn.executemany(
        "INSERT INTO moz_cookies (host, name, value, path, expiry, isSecure, isHttpOnly) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def test_read_chromium_cookies_decrypts_and_filters(tmp_path):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = AESGCM.generate_key(bit_length=256)
    db = tmp_path / "Cookies"
    _make_chromium_db(db, [
        (".google.com", "SID", _aesgcm_v10(key, b"real"), "", "/", 0, 1, 1),
        (".other.com", "X", _aesgcm_v10(key, b"nope"), "", "/", 0, 0, 0),   # filtered by allowlist
        (".google.com", "ABE", b"v20" + os.urandom(30), "", "/", 0, 0, 0),  # counted abe_locked
    ])
    cookies, skipped, abe = PI._read_chromium_cookies(db, key, DomainFilter(["google.com"]))
    names = {c.name: c.value for c in cookies}
    assert names == {"SID": "real"}
    assert skipped == 0 and abe == 1


def test_read_firefox_cookies_plaintext(tmp_path):
    db = tmp_path / "cookies.sqlite"
    _make_firefox_db(db, [
        (".google.com", "PREF", "abc", "/", 9999999999, 0, 0),
        (".yandex.ru", "yp", "def", "/", 0, 1, 1),
        (".spam.com", "junk", "zzz", "/", 0, 0, 0),  # filtered
    ])
    cookies = PI._read_firefox_cookies(db, DomainFilter(["google.com", "yandex.ru"]))
    got = {c.name: c.value for c in cookies}
    assert got == {"PREF": "abc", "yp": "def"}


# ── Domain allowlist ──────────────────────────────────────────────────────────────────

def test_domain_filter_suffix_match_and_empty_allows_all():
    f = DomainFilter(["google.com"])
    assert f.matches(".google.com") and f.matches("www.google.com")
    assert not f.matches("notgoogle.com") and not f.matches("google.com.evil.net")
    assert DomainFilter([]).matches("anything.example")  # empty = all


# ── Default-browser-first ordering ────────────────────────────────────────────────────

def test_default_first_ordering(monkeypatch):
    monkeypatch.setattr(PI, "detect_default_browser", lambda: "firefox")
    assert PI._default_first(["chrome", "edge", "firefox"]) == ["firefox", "chrome", "edge"]
    # Default not in the wanted set → order unchanged.
    monkeypatch.setattr(PI, "detect_default_browser", lambda: "safari")
    assert PI._default_first(["chrome", "firefox"]) == ["chrome", "firefox"]


# ── IdentityStore imported layer ──────────────────────────────────────────────────────

def _store(tmp_path) -> IdentityStore:
    return IdentityStore(str(tmp_path / "ident.db"))


def test_import_first_wins_dedup_and_read(tmp_path):
    store = _store(tmp_path)
    n = store.import_cookies("chromium", [
        ImportedCookie(domain=".google.com", name="SID", value="win", secure=True),
        ImportedCookie(domain=".google.com", name="SID", value="lose"),   # dup → dropped
        ImportedCookie(domain=".yandex.ru", name="yp", value="y", expires=9999999999),
    ], source="chrome")
    assert n == 2
    assert store.imported_cookies_map("chromium", "www.google.com") == {"SID": "win"}
    ss = store.imported_cookies_for("chromium", host="google.com")
    assert ss == [{"name": "SID", "value": "win", "domain": ".google.com", "path": "/", "secure": True}]


def test_expired_imported_cookie_dropped_on_read(tmp_path):
    store = _store(tmp_path)
    store.import_cookies("chromium", [
        ImportedCookie(domain=".google.com", name="live", value="1", expires=9999999999),
        ImportedCookie(domain=".google.com", name="dead", value="0", expires=1),  # past
        ImportedCookie(domain=".google.com", name="sess", value="s", expires=0),  # session, kept
    ])
    got = store.imported_cookies_map("chromium", "google.com")
    assert "live" in got and "sess" in got and "dead" not in got


def test_import_replace_and_clear(tmp_path):
    store = _store(tmp_path)
    store.import_cookies("firefox", [ImportedCookie(domain=".a.com", name="k", value="1")])
    # replace=True wipes the prior set.
    store.import_cookies("firefox", [ImportedCookie(domain=".b.com", name="k2", value="2")])
    assert store.imported_cookies_map("firefox", "a.com") == {}
    assert store.imported_cookies_map("firefox", "b.com") == {"k2": "2"}
    store.clear_imported("firefox")
    assert store.imported_cookies_map("firefox", "b.com") == {}


def test_families_are_isolated(tmp_path):
    store = _store(tmp_path)
    store.import_cookies("chromium", [ImportedCookie(domain=".google.com", name="c", value="1")])
    store.import_cookies("firefox", [ImportedCookie(domain=".google.com", name="f", value="2")])
    assert store.imported_cookies_map("chromium", "google.com") == {"c": "1"}
    assert store.imported_cookies_map("firefox", "google.com") == {"f": "2"}


# ── Transport merge: imported is the BASE layer, earned/seed cookies win ───────────────

def test_transport_merges_imported_as_base_layer(tmp_path, monkeypatch):
    import core.fetch.transport as T

    store = _store(tmp_path)
    store.import_cookies("chromium", [
        ImportedCookie(domain=".qwant.com", name="SID", value="imported"),
        ImportedCookie(domain=".qwant.com", name="CONSENT", value="imported-consent"),
    ])
    # Engine has since earned its own CONSENT (should override the imported one).
    store.merge_set_cookie("qwant", "www.qwant.com", ["CONSENT=earned; Domain=.qwant.com; Max-Age=1000"])
    monkeypatch.setattr("core.fetch.browser.identity_store.get_identity_store", lambda: store)

    req = EngineRequest(
        method="GET", url="https://www.qwant.com/", params={}, headers={},
        cookies={}, primp_target="chrome", primp_os="windows", identity_key="qwant",
    )
    merged = T._replay_identity_cookies(req, "www.qwant.com")
    assert merged.cookies["SID"] == "imported"          # imported fills a session the engine can't earn
    assert merged.cookies["CONSENT"] == "earned"        # earned cookie overrides imported


def test_transport_firefox_family_mapping(tmp_path, monkeypatch):
    import core.fetch.transport as T

    store = _store(tmp_path)
    store.import_cookies("firefox", [ImportedCookie(domain=".duckduckgo.com", name="ff", value="1")])
    monkeypatch.setattr("core.fetch.browser.identity_store.get_identity_store", lambda: store)
    req = EngineRequest(
        method="GET", url="https://duckduckgo.com/", params={}, headers={},
        cookies={}, primp_target="firefox", primp_os="windows", identity_key="duckduckgo",
    )
    merged = T._replay_identity_cookies(req, "duckduckgo.com")
    assert merged.cookies.get("ff") == "1"
    assert T._imported_family("firefox") == "firefox"
    assert T._imported_family("chrome") == "chromium"
    assert T._imported_family("qwant") == ""  # unknown target → no primary family


def test_transport_cross_family_fallback(tmp_path, monkeypatch):
    # A real session for a host may live in the user's Firefox while the engine impersonates
    # Chrome (chromium jar empty under App-Bound enc). The Firefox cookie must still replay:
    # a session cookie is not bound to the TLS fingerprint.
    import core.fetch.transport as T

    store = _store(tmp_path)
    store.import_cookies("firefox", [ImportedCookie(domain=".startpage.com", name="pref", value="ff-session")])
    monkeypatch.setattr("core.fetch.browser.identity_store.get_identity_store", lambda: store)
    req = EngineRequest(
        method="GET", url="https://www.startpage.com/sp/search", params={}, headers={},
        cookies={}, primp_target="chrome", primp_os="windows", identity_key="startpage",
    )
    merged = T._replay_identity_cookies(req, "www.startpage.com")
    assert merged.cookies.get("pref") == "ff-session"


def test_google_gsa_engine_is_denied_imported_cookies(tmp_path, monkeypatch):
    # Google's GSA-UA trick needs a cookie-light identity; imported desktop cookies flip it to
    # the JS layout the parser can't read (verified live). So identity_key="google" is denied.
    import core.fetch.transport as T

    store = _store(tmp_path)
    store.import_cookies("firefox", [ImportedCookie(domain=".google.com", name="SID", value="ff")])
    monkeypatch.setattr("core.fetch.browser.identity_store.get_identity_store", lambda: store)
    req = EngineRequest(
        method="GET", url="https://www.google.com/search", params={}, headers={},
        cookies={}, primp_target="chrome", primp_os="windows", identity_key="google",
    )
    merged = T._replay_identity_cookies(req, "www.google.com")
    assert "SID" not in merged.cookies  # denylisted engine gets no imported cookies


# ── Run-once trigger honours the config switch ────────────────────────────────────────

def test_run_import_disabled_purges(tmp_path, monkeypatch):
    import core.config.settings as S
    from core.config.settings import SearchConfig, ProfileImportSection

    store = _store(tmp_path)
    store.import_cookies("chromium", [ImportedCookie(domain=".x.com", name="k", value="1")])
    monkeypatch.setattr("core.fetch.browser.identity_store.get_identity_store", lambda: store)
    cfg = SearchConfig(profile_import=ProfileImportSection(enabled=False, purge_on_disable=True))
    monkeypatch.setattr(S, "load_search_config", lambda *a, **k: cfg)

    out = PI.run_profile_import(force=True)
    assert out.enabled is False and out.ran is False
    assert store.imported_cookies_map("chromium", "x.com") == {}  # purged
