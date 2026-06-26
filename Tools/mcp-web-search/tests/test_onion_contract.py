# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""The onion opt-in is advertised in the tool schema and honored ONLY when tor.enabled —
the capability config gates the model-facing intent flag."""

from __future__ import annotations

import core.config as cfgmod
from core.config.settings import SearchConfig, TorSection
from core.mcp_contract import build_search_schema, coerce_search_onion


def _tor(monkeypatch, enabled: bool):
    monkeypatch.setattr(cfgmod, "load_search_config",
                        lambda *a, **k: SearchConfig(tor=TorSection(enabled=enabled)))


def test_schema_hides_onion_when_disabled(monkeypatch):
    _tor(monkeypatch, False)
    assert "onion" not in build_search_schema()["properties"]
    assert coerce_search_onion({"onion": True}) is False   # AND-gate: capability off


def test_schema_shows_onion_when_enabled(monkeypatch):
    _tor(monkeypatch, True)
    props = build_search_schema()["properties"]
    assert "onion" in props and props["onion"]["type"] == "boolean"
    assert coerce_search_onion({"onion": True}) is True
    assert coerce_search_onion({"onion": False}) is False


def test_base_schema_unaffected(monkeypatch):
    _tor(monkeypatch, True)
    assert {"query", "effort", "shopping", "academic"} <= set(build_search_schema()["properties"])
