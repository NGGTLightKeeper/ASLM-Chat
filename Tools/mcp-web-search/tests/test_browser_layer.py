# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Offline coverage for the warm-browser layer: identity store, config, client dispatch.

No live browser or daemon — the daemon's browser-driving code needs a real cloakbrowser
and is validated separately; here we pin the store, the config axes, and the backend
dispatch (mocked HTTP) that callers actually depend on.
"""

from __future__ import annotations

import asyncio
import json

from core.config.settings import BrowserSection, load_search_config
from core.fetch.browser.client import BrowserClient
from core.fetch.browser.identity_store import IdentityStore
from core.fetch.browser.models import STATUS_OK, STATUS_UNAVAILABLE, BrowserFetch


# ── identity store ────────────────────────────────────────────────────────────────

def _state(*cookies: dict) -> dict:
    return {"cookies": list(cookies), "origins": []}


def test_identity_checkpoint_and_latest_good(tmp_path):
    store = IdentityStore(str(tmp_path / "id.db"))
    assert store.latest_good("google") is None
    gen = store.checkpoint("google", _state({"name": "NID", "value": "1", "domain": ".google.com"}))
    assert gen == 1
    state = store.latest_good("google")
    assert state and state["cookies"][0]["name"] == "NID"


def test_identity_prune_keeps_newest_good(tmp_path):
    store = IdentityStore(str(tmp_path / "id.db"), max_generations=2)
    for i in range(5):
        store.checkpoint("yandex", _state({"name": f"c{i}", "value": str(i), "domain": "yandex.ru"}))
    # Only the 2 newest generations survive pruning.
    rows = store._get_conn().execute(
        "SELECT generation FROM identity_generations WHERE family = 'yandex' ORDER BY generation"
    ).fetchall()
    assert [r["generation"] for r in rows] == [4, 5]


def test_identity_rotate_burns_latest_and_falls_back(tmp_path):
    store = IdentityStore(str(tmp_path / "id.db"))
    store.checkpoint("brave", _state({"name": "old", "value": "1", "domain": "search.brave.com"}))
    store.checkpoint("brave", _state({"name": "new", "value": "2", "domain": "search.brave.com"}))
    # Rotate burns the newest (gen 2) and returns the older good generation (gen 1).
    fallback = store.rotate("brave")
    assert fallback and fallback["cookies"][0]["name"] == "old"
    # The burned generation is no longer the "latest good".
    assert store.latest_good("brave")["cookies"][0]["name"] == "old"


def test_identity_rotate_with_no_fallback_returns_none(tmp_path):
    store = IdentityStore(str(tmp_path / "id.db"))
    store.checkpoint("ddg", _state({"name": "only", "value": "1", "domain": "duckduckgo.com"}))
    assert store.rotate("ddg") is None  # nothing good left → caller falls back to seed


def test_identity_cookie_header_is_host_scoped(tmp_path):
    store = IdentityStore(str(tmp_path / "id.db"))
    store.checkpoint(
        "google",
        _state(
            {"name": "NID", "value": "abc", "domain": ".google.com"},
            {"name": "other", "value": "x", "domain": "example.com"},
        ),
    )
    header = store.cookie_header_for("google", "www.google.com")
    assert header == "NID=abc"  # example.com cookie excluded by host scoping


# ── config axes ──────────────────────────────────────────────────────────────────

def test_browser_section_defaults():
    sec = BrowserSection()
    assert sec.browser_fallback == "page"
    assert sec.browser_backend == "warm"
    assert sec.max_rss_mb == 2048


def test_browser_config_validates_enums(tmp_path):
    cfg_path = tmp_path / "search_config.json"
    cfg_path.write_text(
        json.dumps({"browser": {"browser_fallback": "bogus", "browser_backend": "legacy"}}),
        encoding="utf-8",
    )
    cfg = load_search_config(path=cfg_path)
    assert cfg.browser.browser_fallback == "page"   # invalid → safe default
    assert cfg.browser.browser_backend == "legacy"  # valid value preserved


# ── client dispatch (mocked daemon) ────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, body: dict, status: int = 200) -> None:
        self._body = body
        self.status_code = status

    def json(self) -> dict:
        return self._body


class _FakeHttp:
    def __init__(self, body: dict) -> None:
        self._body = body
        self.posted: dict | None = None

    async def get(self, url: str) -> _FakeResp:
        return _FakeResp({"engines": []})

    async def post(self, url: str, json: dict) -> _FakeResp:  # noqa: A002 — mirror httpx kwarg
        self.posted = json
        return _FakeResp(self._body)


def test_client_off_returns_unavailable():
    client = BrowserClient(cfg=BrowserSection(browser_fallback="off"))
    result = asyncio.run(client.fetch("https://example.com"))
    assert result.status == STATUS_UNAVAILABLE


def test_client_warm_dispatches_to_daemon():
    client = BrowserClient(cfg=BrowserSection(browser_fallback="page", browser_backend="warm"))
    fake = _FakeHttp({"url": "https://example.com", "status": "ok", "html": "<html>hi</html>", "ms": 12.0})
    client._http = fake
    result = asyncio.run(client.fetch("https://example.com", wait_sec=2.0))
    assert isinstance(result, BrowserFetch)
    assert result.status == STATUS_OK and result.ok and result.backend == "warm"
    assert fake.posted["wait_ms"] == 2000 and fake.posted["engine"] == "chromium"


def test_client_warm_unreachable_is_unavailable_not_crash():
    client = BrowserClient(cfg=BrowserSection(browser_backend="warm"))

    class _Boom:
        async def post(self, *a, **k):
            raise ConnectionError("daemon down")

        async def get(self, *a, **k):
            raise ConnectionError("daemon down")

    client._http = _Boom()
    result = asyncio.run(client.fetch("https://example.com"))
    assert result.status == STATUS_UNAVAILABLE
    assert asyncio.run(client.available()) is False
