# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Onion layer — resolver gating + transport, all offline.

No tor and no network: sockets/binary-discovery/curl are faked so we lock in the rules that
must hold — disabled is a no-op, a running tor is reused before spawning, no binary disables
the feature, and fetch degrades gracefully when no SOCKS is available.
"""

from __future__ import annotations

import asyncio

import curl_cffi

import core.config as cfgmod
import core.fetch.onion.tor_proxy as tp
from core.config.settings import SearchConfig, TorSection
from core.fetch.onion import transport


def _use_cfg(monkeypatch, **tor_kw):
    cfg = SearchConfig(tor=TorSection(**tor_kw))
    monkeypatch.setattr(cfgmod, "load_search_config", lambda *a, **k: cfg)
    tp._resolved = tp._UNSET  # drop resolver cache


def test_disabled_is_noop(monkeypatch):
    _use_cfg(monkeypatch, enabled=False)
    assert tp.resolve_socks() is None


def test_reuses_running_tor_before_spawning(monkeypatch):
    _use_cfg(monkeypatch, enabled=True, spawn_own=True)
    monkeypatch.setattr(tp, "_port_open", lambda h, p, timeout=1.0: p == 9050)
    spawned = {"called": False}
    monkeypatch.setattr(tp, "_spawn_tor", lambda *a, **k: spawned.__setitem__("called", True))
    assert tp.resolve_socks() == "socks5h://127.0.0.1:9050"
    assert spawned["called"] is False  # never spawned — a running tor was reused


def test_spawns_from_discovered_binary_when_none_running(monkeypatch):
    _use_cfg(monkeypatch, enabled=True, spawn_own=True)
    monkeypatch.setattr(tp, "_port_open", lambda h, p, timeout=1.0: False)
    monkeypatch.setattr(tp, "discover_tor_binary", lambda override="": "/usr/bin/tor")
    monkeypatch.setattr(tp, "_spawn_tor", lambda binary, **k: "socks5h://127.0.0.1:9250")
    assert tp.resolve_socks() == "socks5h://127.0.0.1:9250"


def test_no_binary_keeps_feature_disabled(monkeypatch):
    _use_cfg(monkeypatch, enabled=True, spawn_own=True)
    monkeypatch.setattr(tp, "_port_open", lambda h, p, timeout=1.0: False)
    monkeypatch.setattr(tp, "discover_tor_binary", lambda override="": None)
    assert tp.resolve_socks() is None  # zero-install: no tor present → no-op


def test_discover_binary_override(tmp_path):
    real = tmp_path / "tor"
    real.write_text("x")
    assert tp.discover_tor_binary(str(real)) == str(real)
    assert tp.discover_tor_binary(str(tmp_path / "missing")) is None


def test_fetch_unavailable_when_no_socks(monkeypatch):
    monkeypatch.setattr(transport, "resolve_socks", lambda force=False: None)
    r = asyncio.run(transport.onion_fetch("http://x.onion/", timeout=5))
    assert r.status == "unavailable" and r.ok is False


def test_fetch_ok_over_fake_tor(monkeypatch):
    monkeypatch.setattr(transport, "resolve_socks",
                        lambda force=False: "socks5h://127.0.0.1:9150")

    class _Resp:
        status_code = 200
        text = "<html>onion body</html>"

    class _Fake:
        def get(self, url, **kw):
            return _Resp()

    monkeypatch.setattr(curl_cffi, "requests", _Fake())
    r = asyncio.run(transport.onion_fetch("http://x.onion/", timeout=5))
    assert r.ok and r.status == "ok" and r.http_status == 200
    assert "onion body" in r.text


# ── discovery: structural matcher + OS standard indexer ─────────────────────────────

def test_looks_like_tb_tor_matcher(tmp_path):
    good = tmp_path / "Tor Browser" / "Browser" / "TorBrowser" / "Tor" / "tor.exe"
    good.parent.mkdir(parents=True)
    good.write_text("x")
    assert tp._looks_like_tb_tor(str(good), "tor.exe")
    no_marker = tmp_path / "random" / "Tor" / "tor.exe"
    no_marker.parent.mkdir(parents=True)
    no_marker.write_text("x")
    assert not tp._looks_like_tb_tor(str(no_marker), "tor.exe")          # no "tor browser" marker
    assert not tp._looks_like_tb_tor(str(good) + "_missing", "tor.exe")  # not a real file


def test_indexer_noop_on_windows(monkeypatch):
    monkeypatch.setattr(tp.sys, "platform", "win32")
    assert tp._indexer_lookup() is None   # no Everything dependency → falls back to scan


def test_indexer_parses_locate_on_linux(tmp_path, monkeypatch):
    import types
    real = tmp_path / "tor-browser_en-US" / "Browser" / "TorBrowser" / "Tor" / "tor"
    real.parent.mkdir(parents=True)
    real.write_text("x")
    monkeypatch.setattr(tp.sys, "platform", "linux")
    monkeypatch.setattr(tp.shutil, "which", lambda n: "/usr/bin/plocate" if n == "plocate" else None)
    monkeypatch.setattr(tp.subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(stdout=f"/noise/tor\n{real}\n"))
    assert tp._indexer_lookup() == str(real)


# ── spawned-tor idle shutdown (mirrors warm browser) ───────────────────────────────

def test_reap_if_idle(monkeypatch):
    import types
    calls = {"term": 0}
    monkeypatch.setattr(tp, "_terminate", lambda: calls.__setitem__("term", calls["term"] + 1))
    monkeypatch.setattr(tp, "_proc", types.SimpleNamespace(poll=lambda: None))

    tp.mark_used()                                  # fresh activity
    assert tp._reap_if_idle(900) is False           # not idle → keep
    assert calls["term"] == 0

    tp._last_used = tp.time.monotonic() - 1000       # idle past 900s
    assert tp._reap_if_idle(900) is True            # reaped
    assert calls["term"] == 1
    assert tp._resolved is tp._UNSET                # cache reset → re-resolve next time

    monkeypatch.setattr(tp, "_proc", types.SimpleNamespace(poll=lambda: None))
    tp._last_used = tp.time.monotonic() - 10000
    assert tp._reap_if_idle(0) is False             # 0 = never reap


def test_resolved_default_is_unset_not_none():
    # regression guard: the module must initialize _resolved to the _UNSET sentinel. If it
    # were None, the very first resolve_socks() returns that cached None and never probes or
    # spawns — the onion layer would always report "unavailable".
    import importlib
    importlib.reload(tp)
    assert tp._resolved is tp._UNSET


def test_prewarm_gating_and_background(monkeypatch):
    def cfg(enabled, prewarm):
        return lambda *a, **k: SearchConfig(tor=TorSection(enabled=enabled, prewarm=prewarm))

    def fake_resolve(force=False):
        tp._resolved = "socks5h://127.0.0.1:9250"
        return tp._resolved

    monkeypatch.setattr(tp, "resolve_socks", fake_resolve)

    # prewarm off → no-op (no thread, nothing resolved)
    monkeypatch.setattr(cfgmod, "load_search_config", cfg(True, False))
    tp._resolved = tp._UNSET; tp._warming = False; tp._last_used = 0.0; tp._warm_thread = None
    tp.prewarm()
    assert tp._warm_thread is None and tp._resolved is tp._UNSET

    # on + pristine → warms in a background thread
    monkeypatch.setattr(cfgmod, "load_search_config", cfg(True, True))
    tp.prewarm()
    assert tp._warm_thread is not None
    tp._warm_thread.join(timeout=3)
    assert tp._resolved == "socks5h://127.0.0.1:9250"
    assert tp._last_used > 0 and tp._warming is False

    # already warm → just refreshes idle timer, no new thread
    tp._warm_thread = None; tp._last_used = 0.0
    tp.prewarm()
    assert tp._warm_thread is None and tp._last_used > 0
