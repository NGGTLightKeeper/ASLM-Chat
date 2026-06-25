# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Anchored auto-expansion — store, harvester gating, and registry merge, all offline.

Locks in the safety rules: disabled is a no-op, only clearnet anchors that self-publish an
Onion-Location are admitted, seed-covered domains are skipped, and harvested entries merge
into the registry without overriding the hand-vetted seed.
"""

from __future__ import annotations

import curl_cffi

import core.config as cfgmod
import core.fetch.onion.store as store_mod
from core.config.settings import SearchConfig, TorSection
from core.fetch.onion import harvester, registry
from core.fetch.onion.models import OnionService
from core.fetch.onion.store import OnionStore


def _set_auto_expand(monkeypatch, on: bool):
    monkeypatch.setattr(cfgmod, "load_search_config",
                        lambda *a, **k: SearchConfig(tor=TorSection(enabled=True, auto_expand=on)))


class _Resp:
    def __init__(self, headers):
        self.headers = headers


class _FakeCurl:
    """Maps clearnet anchor host -> Onion-Location value (None = no header)."""
    def __init__(self, mapping):
        self._m = mapping

    def get(self, url, **kw):
        for host, hv in self._m.items():
            if host in url:
                return _Resp({"onion-location": hv} if hv else {})
        return _Resp({})


def test_store_upsert_list_age(tmp_path):
    st = OnionStore(str(tmp_path / "o.db"))
    st.upsert(OnionService("x", "harvested", "https://x.example/", "http://a.onion/"))
    assert len(st.list_all()) == 1
    assert st.age_of("x") is not None and st.age_of("nope") is None
    st.upsert(OnionService("x", "harvested", "https://x.example/", "http://b.onion/"))  # update
    rows = st.list_all()
    assert len(rows) == 1 and rows[0].onion == "http://b.onion/"


def test_harvest_disabled_is_noop(monkeypatch, tmp_path):
    _set_auto_expand(monkeypatch, False)
    st = OnionStore(str(tmp_path / "o.db"))
    res = harvester.harvest(store=st, anchors=("https://www.propublica.org/",))
    assert res["disabled"] == 1
    assert len(st.list_all()) == 0


def test_harvest_admits_only_self_publishing(monkeypatch, tmp_path):
    _set_auto_expand(monkeypatch, True)
    monkeypatch.setattr(curl_cffi, "requests", _FakeCurl({
        "propublica.org": "http://propubonion0000000000000000000000000000000000000000.onion/",
        "nytimes.com": None,   # advertises nothing → not admitted
    }))
    st = OnionStore(str(tmp_path / "o.db"))
    res = harvester.harvest(store=st, anchors=(
        "https://www.propublica.org/", "https://www.nytimes.com/",
    ))
    assert res["admitted"] == 1 and res["no_onion"] == 1
    assert {s.name for s in st.list_all()} == {"propublica"}


def test_harvest_skips_seed_covered_domains(monkeypatch, tmp_path):
    _set_auto_expand(monkeypatch, True)
    monkeypatch.setattr(curl_cffi, "requests", _FakeCurl({"theguardian.com": "http://x.onion/"}))
    st = OnionStore(str(tmp_path / "o.db"))
    res = harvester.harvest(store=st, anchors=("https://www.theguardian.com/",))
    assert res["skipped"] == 1 and res["admitted"] == 0  # already in the hand-vetted seed


def test_registry_merges_store_with_seed_precedence(monkeypatch, tmp_path):
    st = OnionStore(str(tmp_path / "o.db"))
    st.upsert(OnionService("propublica", "harvested", "https://propublica.org/", "http://pp.onion/"))
    st.upsert(OnionService("guardian", "harvested", "https://evil.example/", "http://evil.onion/"))
    monkeypatch.setattr(store_mod, "get_onion_store", lambda: st)

    services = {s.name: s for s in registry.load_services()}
    assert "propublica" in services            # harvested entry surfaced
    assert "guardian" in services               # seed entry present
    assert "theguardian.com" in services["guardian"].clearnet_anchor  # seed wins, not evil
