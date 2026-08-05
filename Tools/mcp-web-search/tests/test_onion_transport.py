# Copyright NEXTGGTECH. Elastic License 2.0.

"""Onion layer — SOCKS resolution (reuse-only) + transport, all offline.

No tor and no network: sockets/curl are faked so we lock in the rules that must hold —
disabled is a no-op, an explicit socks_url and a running tor are reused, no running tor
disables the feature (we never spawn), and fetch degrades gracefully without a SOCKS.
"""

from __future__ import annotations

import asyncio

import curl_cffi
import curl_cffi.requests  # noqa: F401  - bind the submodule so monkeypatch.setattr finds it

import core.config as cfgmod
import core.fetch.onion.tor_proxy as tp
from core.config.settings import SearchConfig, TorSection
from core.fetch.onion import transport


def _use_cfg(monkeypatch, **tor_kw):
    cfg = SearchConfig(tor=TorSection(**tor_kw))
    monkeypatch.setattr(cfgmod, "load_search_config", lambda *a, **k: cfg)
    tp.reset()  # drop resolver cache


def test_disabled_is_noop(monkeypatch):
    _use_cfg(monkeypatch, enabled=False)
    assert tp.resolve_socks() is None


def test_reuses_running_tor(monkeypatch):
    _use_cfg(monkeypatch, enabled=True)
    monkeypatch.setattr(tp, "_port_open", lambda h, p, timeout=1.0: p == 9050)
    assert tp.resolve_socks() == "socks5h://127.0.0.1:9050"


def test_prefers_tor_browser_when_only_9150(monkeypatch):
    _use_cfg(monkeypatch, enabled=True)
    monkeypatch.setattr(tp, "_port_open", lambda h, p, timeout=1.0: p == 9150)
    assert tp.resolve_socks() == "socks5h://127.0.0.1:9150"


def test_explicit_socks_url_used_when_answering(monkeypatch):
    _use_cfg(monkeypatch, enabled=True, socks_url="socks5h://127.0.0.1:9999")
    monkeypatch.setattr(tp, "_port_open", lambda h, p, timeout=1.0: p == 9999)
    assert tp.resolve_socks() == "socks5h://127.0.0.1:9999"


def test_no_running_tor_keeps_feature_disabled(monkeypatch):
    _use_cfg(monkeypatch, enabled=True)
    monkeypatch.setattr(tp, "_port_open", lambda h, p, timeout=1.0: False)
    assert tp.resolve_socks() is None  # we never spawn — no running tor → no-op


def test_resolution_is_cached_until_reset(monkeypatch):
    _use_cfg(monkeypatch, enabled=True)
    calls = {"n": 0}

    def probe(h, p, timeout=1.0):
        calls["n"] += 1
        return p == 9050

    monkeypatch.setattr(tp, "_port_open", probe)
    assert tp.resolve_socks() == "socks5h://127.0.0.1:9050"
    n_after_first = calls["n"]
    assert tp.resolve_socks() == "socks5h://127.0.0.1:9050"  # served from cache
    assert calls["n"] == n_after_first                       # no re-probe
    assert tp.resolve_socks(force=True) == "socks5h://127.0.0.1:9050"
    assert calls["n"] > n_after_first                        # force re-probes


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


def test_resolved_default_is_unset_not_none():
    # regression guard: the module must initialize _resolved to the _UNSET sentinel. If it
    # were None, the very first resolve_socks() returns that cached None and never probes —
    # the onion layer would always report "unavailable".
    import importlib
    importlib.reload(tp)
    assert tp._resolved is tp._UNSET
