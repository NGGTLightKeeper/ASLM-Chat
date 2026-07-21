# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import core.config as config_module
import core.search.web_search as search_module
from core.mcp_contract import build_search_description, build_search_schema, prepare_search_arguments
from core.query.search_plan import PlanValidationError, prepare_advanced_search
from core.search.query_dates import resolve_query_dates


def _config(*, mode: str = "advanced", tor: bool = False):
    return SimpleNamespace(
        query=SimpleNamespace(
            schema_mode=mode,
            ui_display_mode="compiled_query",
            year_hint_mode="timelimit",
            year_hint_current="m",
            year_hint_prev="y",
            year_hint_older=None,
        ),
        tor=SimpleNamespace(enabled=tor),
    )


def _plan():
    return {
        "queries": [
            {
                "purpose": "currency conversion",
                "vertical": "web",
                "text": "10000 RUB USD exchange rate",
                "operators": {
                    "exact_phrases": ["central bank rate"],
                    "any_terms": ["official", "reference"],
                    "exclude_terms": ["archive copy"],
                    "site_include": ["www.example.com", "docs.example.org"],
                    "site_exclude": ["old.example.com"],
                    "file_types": [".PDF", "csv"],
                    "title_terms": ["exchange rates"],
                    "url_terms": ["rates"],
                    "after": "2026-07-01",
                    "before": "2026-07-22",
                },
            }
        ],
        "effort": "medium",
    }


def test_config_schema_mode_defaults_and_invalid_values_fall_back_to_advanced(tmp_path, caplog):
    from core.config.settings import load_search_config

    missing = tmp_path / "missing.json"
    assert load_search_config(missing).query.schema_mode == "advanced"
    assert load_search_config(missing).query.ui_display_mode == "compiled_query"

    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"query": {"schema_mode": "unknown"}}), encoding="utf-8")
    assert load_search_config(invalid).query.schema_mode == "advanced"
    assert "invalid value" in caplog.text

    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"query": {"schema_mode": "legacy"}}), encoding="utf-8")
    assert load_search_config(legacy).query.schema_mode == "legacy"

    purpose = tmp_path / "purpose.json"
    purpose.write_text(json.dumps({"query": {"ui_display_mode": "purpose"}}), encoding="utf-8")
    assert load_search_config(purpose).query.ui_display_mode == "purpose"

    invalid_ui = tmp_path / "invalid-ui.json"
    invalid_ui.write_text(json.dumps({"query": {"ui_display_mode": "both"}}), encoding="utf-8")
    assert load_search_config(invalid_ui).query.ui_display_mode == "compiled_query"


def test_advanced_schema_is_default_and_onion_is_capability_gated(monkeypatch):
    monkeypatch.setattr(config_module, "load_search_config", lambda: _config(tor=False))
    schema = build_search_schema()
    item = schema["properties"]["queries"]["items"]
    assert schema["required"] == ["queries"]
    assert schema["properties"]["queries"]["maxItems"] == 4
    assert item["required"] == ["purpose", "vertical", "text"]
    assert item["properties"]["vertical"]["enum"] == ["web", "shopping", "academic"]
    assert "structured plan" in build_search_description()

    monkeypatch.setattr(config_module, "load_search_config", lambda: _config(tor=True))
    assert "onion" in build_search_schema()["properties"]["queries"]["items"]["properties"]["vertical"]["enum"]


def test_advanced_compiler_covers_every_operator_and_normalizes_stably():
    prepared = prepare_advanced_search(_plan(), query_config=_config().query)
    query = prepared["search_request"]["queries"][0]["compiled_query"]
    assert query == (
        '10000 RUB USD exchange rate "central bank rate" (official OR reference) '
        '-"archive copy" (site:example.com OR site:docs.example.org) '
        '-site:old.example.com (filetype:pdf OR filetype:csv) '
        'intitle:"exchange rates" inurl:rates after:2026-07-01 before:2026-07-22'
    )
    assert prepared["canonical_arguments"]["queries"][0]["operators"]["site_include"] == [
        "example.com",
        "docs.example.org",
    ]


def test_advanced_plan_rejects_legacy_shape_and_is_atomic(monkeypatch):
    monkeypatch.setattr(config_module, "load_search_config", lambda: _config())
    rejected = prepare_search_arguments({"query": "legacy query"})
    assert rejected["ok"] is False
    assert rejected["error_result"]["error"]["code"] == "INVALID_SEARCH_PLAN"

    plan = _plan()
    plan["queries"].append({"purpose": "bad", "vertical": "web", "text": "query site:example.com"})
    with pytest.raises(PlanValidationError) as exc:
        prepare_advanced_search(plan, query_config=_config().query)
    assert any(issue["path"].endswith(".text") for issue in exc.value.issues)


def test_preflight_advertises_configured_ui_display_mode(monkeypatch):
    cfg = _config()
    cfg.query.ui_display_mode = "purpose"
    monkeypatch.setattr(config_module, "load_search_config", lambda: cfg)

    prepared = prepare_search_arguments(_plan())

    assert prepared["tool_ui"]["query_display_mode"] == "purpose"


def test_explicit_date_operators_survive_legacy_year_hint_processing():
    query = "latest pricing after:2026-01-01 before:2026-07-01"
    clean, _timelimit = resolve_query_dates(query, _config().query)
    assert "after:2026-01-01" in clean
    assert "before:2026-07-01" in clean


def test_mixed_vertical_plan_runs_concurrently_and_preserves_metadata(monkeypatch):
    active = 0
    max_active = 0
    calls: list[tuple[str, dict]] = []

    async def fake_search(query: str, **kwargs):
        nonlocal active, max_active
        calls.append((query, kwargs))
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {
            "search_id": f"id-{len(calls)}",
            "language": "en",
            "region": "us-en",
            "engines_used": ["fake"],
            "cached": False,
            "sources": [{"url": f"https://example.com/{len(calls)}", "host": "example.com", "title": query, "snippet": query}],
        }

    monkeypatch.setattr(search_module, "run_web_search", fake_search)
    request = {
        "schema_mode": "advanced",
        "effort": "medium",
        "queries": [
            {"purpose": "independent evidence", "vertical": "web", "compiled_query": "alpha", "operators": {}, "timelimit": None},
            {"purpose": "price check", "vertical": "shopping", "compiled_query": "beta", "operators": {}, "timelimit": None},
            {"purpose": "papers", "vertical": "academic", "compiled_query": "gamma", "operators": {}, "timelimit": None},
            {"purpose": "verification", "vertical": "web", "compiled_query": "delta", "operators": {}, "timelimit": None},
        ],
    }
    result = asyncio.run(search_module.run_web_search_plan(request))

    assert max_active == 4
    assert calls[0][1]["shopping"] is False
    assert calls[1][1]["shopping"] is True
    assert calls[2][1]["academic"] is True
    assert result["ui"]["search_request"]["queries"][1]["purpose"] == "price check"
    assert result["query_results"][2]["index"] == 3
    assert result["query_results"][2]["vertical"] == "academic"
    assert result["sources"][0]["batch_query_purpose"] == "independent evidence"
    assert result["sources"][0]["query_index"] == 1
    assert result["sources"][0]["purpose"] == "independent evidence"
    assert result["sources"][0]["vertical"] == "web"
    assert len({source["id"] for source in result["sources"]}) == 4
