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
            year_hint_mode="timelimit",
            year_hint_current="m",
            year_hint_prev="y",
            year_hint_older=None,
        ),
        tor=SimpleNamespace(enabled=tor),
    )


def _plan():
    return {
        "description": "Convert reference currency",
        "queries": [
            {
                "vertical": "web",
                "text": "10000 RUB USD exchange rate",
                "operators": {
                    "exact_phrases": ["central bank rate"],
                    "or_terms": ["official", "reference"],
                    "or_groups": [["daily", "monthly"], ["published", "released"]],
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

    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"query": {"schema_mode": "unknown"}}), encoding="utf-8")
    assert load_search_config(invalid).query.schema_mode == "advanced"
    assert "invalid value" in caplog.text

    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"query": {"schema_mode": "legacy"}}), encoding="utf-8")
    assert load_search_config(legacy).query.schema_mode == "legacy"

def test_advanced_schema_is_default_and_onion_is_capability_gated(monkeypatch):
    monkeypatch.setattr(config_module, "load_search_config", lambda: _config(tor=False))
    schema = build_search_schema()
    item = schema["properties"]["queries"]["items"]
    assert schema["required"] == ["description", "queries"]
    assert schema["properties"]["description"]["maxLength"] == 80
    assert "Visible activity title" in schema["properties"]["description"]["description"]
    assert "beginning with an action verb" in schema["properties"]["description"]["description"]
    assert "make sense without the query text" in schema["properties"]["description"]["description"]
    assert schema["properties"]["queries"]["maxItems"] == 14
    assert item["required"] == ["vertical", "text"]
    assert "Never include a four-digit calendar year" in item["properties"]["text"]["description"]
    assert "Required routing from the research plan" in item["properties"]["vertical"]["description"]
    assert "MUST use shopping" in item["properties"]["vertical"]["description"]
    assert "MUST use academic" in item["properties"]["vertical"]["description"]
    assert item["properties"]["operators"]["properties"]["or_groups"]["items"]["minItems"] == 2
    assert "selected by the research plan" in (
        item["properties"]["operators"]["properties"]["site_include"]["items"]["description"]
    )
    assert item["properties"]["vertical"]["enum"] == ["web", "shopping", "academic"]
    assert "Description is the visible activity title" in build_search_description()
    description = build_search_description()
    assert "2 web queries, 4 shopping queries, and 8 academic queries" in description

    monkeypatch.setattr(config_module, "load_search_config", lambda: _config(tor=True))
    assert "onion" in build_search_schema()["properties"]["queries"]["items"]["properties"]["vertical"]["enum"]


def test_advanced_compiler_covers_every_operator_and_normalizes_stably():
    prepared = prepare_advanced_search(_plan(), query_config=_config().query)
    query = prepared["search_request"]["queries"][0]["compiled_query"]
    assert query == (
        '10000 RUB USD exchange rate "central bank rate" (official OR reference) '
        '(daily OR monthly) (published OR released) '
        '-"archive copy" (site:example.com OR site:docs.example.org) '
        '-site:old.example.com (filetype:pdf OR filetype:csv) '
        'intitle:"exchange rates" inurl:rates after:2026-07-01 before:2026-07-22'
    )
    assert prepared["canonical_arguments"]["queries"][0]["operators"]["site_include"] == [
        "example.com",
        "docs.example.org",
    ]
    assert prepared["canonical_arguments"]["description"] == "Convert reference currency"


def test_advanced_plan_rejects_legacy_shape_and_is_atomic(monkeypatch):
    monkeypatch.setattr(config_module, "load_search_config", lambda: _config())
    rejected = prepare_search_arguments({"query": "legacy query"})
    assert rejected["ok"] is False
    assert rejected["error_result"]["error"]["code"] == "INVALID_SEARCH_PLAN"

    plan = _plan()
    plan["queries"].append({"vertical": "web", "text": "query site:example.com"})
    with pytest.raises(PlanValidationError) as exc:
        prepare_advanced_search(plan, query_config=_config().query)
    assert any(issue["path"].endswith(".text") for issue in exc.value.issues)


def test_preflight_advertises_normalized_activity_description(monkeypatch):
    monkeypatch.setattr(config_module, "load_search_config", lambda: _config())

    prepared = prepare_search_arguments(_plan())

    assert prepared["arguments"]["description"] == "Convert reference currency"
    assert prepared["tool_ui"]["description"] == "Convert reference currency"
    assert prepared["tool_ui"]["search_request"]["description"] == "Convert reference currency"


def test_advanced_plan_rejects_missing_description_and_invalid_or_group():
    plan = _plan()
    del plan["description"]
    plan["queries"][0]["operators"]["or_groups"] = [["only one"]]

    with pytest.raises(PlanValidationError) as exc:
        prepare_advanced_search(plan, query_config=_config().query)

    paths = {issue["path"] for issue in exc.value.issues}
    assert "$.description" in paths
    assert "$.queries[0].operators.or_groups[0]" in paths


def test_advanced_plan_enforces_per_vertical_quotas_atomically():
    plan = _plan()
    plan["queries"].extend(
        {"vertical": "web", "text": f"web intent {index}", "operators": {}}
        for index in range(2, 4)
    )

    with pytest.raises(PlanValidationError) as exc:
        prepare_advanced_search(plan, query_config=_config().query)

    assert exc.value.issues == [
        {
            "path": "$.queries[2].vertical",
            "message": "web permits at most 2 queries per call",
        }
    ]


def test_advanced_plan_accepts_full_per_vertical_quotas():
    plan = {
        "description": "Compare products and studies",
        "queries": [
            *(
                {"vertical": "web", "text": f"web evidence {index}", "operators": {}}
                for index in range(2)
            ),
            *(
                {"vertical": "shopping", "text": f"product {index}", "operators": {}}
                for index in range(4)
            ),
            *(
                {"vertical": "academic", "text": f"study topic {index}", "operators": {}}
                for index in range(8)
            ),
        ],
        "effort": "medium",
    }

    prepared = prepare_advanced_search(plan, query_config=_config().query)

    assert len(prepared["search_request"]["queries"]) == 14
    assert sum(q["vertical"] == "web" for q in prepared["search_request"]["queries"]) == 2
    assert sum(q["vertical"] == "shopping" for q in prepared["search_request"]["queries"]) == 4
    assert sum(q["vertical"] == "academic" for q in prepared["search_request"]["queries"]) == 8


@pytest.mark.parametrize(("vertical", "limit"), [("shopping", 4), ("academic", 8)])
def test_advanced_plan_rejects_specialized_vertical_over_quota(vertical, limit):
    plan = {
        "description": "Check specialized evidence",
        "queries": [
            {"vertical": vertical, "text": f"target {index}", "operators": {}}
            for index in range(limit + 1)
        ],
        "effort": "medium",
    }

    with pytest.raises(PlanValidationError) as exc:
        prepare_advanced_search(plan, query_config=_config().query)

    assert exc.value.issues == [
        {
            "path": f"$.queries[{limit}].vertical",
            "message": f"{vertical} permits at most {limit} queries per call",
        }
    ]


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
        "description": "Compare evidence sources",
        "effort": "medium",
        "queries": [
            {
                "vertical": "web", "text": "alpha", "compiled_query": "alpha after:2026-07-01",
                "operators": {"after": "2026-07-01"}, "timelimit": None,
            },
            {
                "vertical": "shopping", "text": "beta", "compiled_query": "beta",
                "operators": {}, "timelimit": None,
            },
        ],
    }
    result = asyncio.run(search_module.run_web_search_plan(request))

    assert max_active == 2
    assert calls[0][1]["shopping"] is False
    assert calls[1][1]["shopping"] is True
    assert calls[0][1]["query_text"] == "alpha"
    assert calls[0][1]["operators"] == {"after": "2026-07-01"}
    assert result["ui"]["description"] == "Compare evidence sources"
    assert result["ui"]["search_request"]["description"] == "Compare evidence sources"
    assert result["query_results"][1]["index"] == 2
    assert result["query_results"][1]["vertical"] == "shopping"
    assert result["sources"][0]["query_index"] == 1
    assert result["sources"][0]["vertical"] == "web"
    assert len({source["id"] for source in result["sources"]}) == 2
