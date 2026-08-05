# Copyright NEXTGGTECH. Elastic License 2.0.

"""Onion allowlist registry + address resolver, offline.

The seed must load into vetted records, lookups must work, and the resolver must prefer a
fresh Onion-Location from the clearnet anchor, cache it, and fall back to the seeded address
when the anchor is unreachable — all without touching the network or Tor.
"""

from __future__ import annotations

import curl_cffi
import curl_cffi.requests  # noqa: F401  - bind the submodule so monkeypatch.setattr finds it

from core.fetch.onion import registry, resolver
from core.fetch.onion.models import OnionService


def test_seed_loads_vetted_services():
    svcs = registry.load_services()
    assert len(svcs) >= 11
    for s in svcs:
        assert s.clearnet_anchor.startswith("https://")  # trust anchor must be TLS
        assert ".onion" in s.onion
        assert s.category


def test_lookup_helpers():
    assert registry.service_for("torproject") is not None
    assert registry.service_for("NOPE") is None
    media = registry.services_in("media")
    assert {s.name for s in media} >= {"guardian", "rferl", "dw"}


_SVC = OnionService(
    name="demo", category="media",
    clearnet_anchor="https://demo.example/",
    onion="http://seedaddr0000000000000000000000000000000000000000000000.onion/",
)


class _Resp:
    def __init__(self, headers):
        self.headers = headers


class _Fake:
    def __init__(self, header_value):
        self.calls = 0
        self._hv = header_value

    def get(self, url, **kw):
        self.calls += 1
        return _Resp({"onion-location": self._hv} if self._hv else {})


def test_resolver_prefers_fresh_and_caches(monkeypatch):
    resolver.reset_cache()
    fresh = "http://freshaddr1111111111111111111111111111111111111111111.onion/"
    fake = _Fake(fresh)
    monkeypatch.setattr(curl_cffi, "requests", fake)
    assert resolver.resolve_onion(_SVC) == fresh          # refreshed from anchor
    assert resolver.resolve_onion(_SVC) == fresh          # served from cache
    assert fake.calls == 1                                # only one network hit


def test_resolver_falls_back_to_seed(monkeypatch):
    resolver.reset_cache()
    fake = _Fake(None)                                    # anchor advertises nothing
    monkeypatch.setattr(curl_cffi, "requests", fake)
    assert resolver.resolve_onion(_SVC) == _SVC.onion     # seeded fallback


def test_resolver_force_refetches(monkeypatch):
    resolver.reset_cache()
    fresh = "http://addr222.onion/"
    fake = _Fake(fresh)
    monkeypatch.setattr(curl_cffi, "requests", fake)
    resolver.resolve_onion(_SVC)
    resolver.resolve_onion(_SVC, force=True)
    assert fake.calls == 2                                # force bypasses cache
