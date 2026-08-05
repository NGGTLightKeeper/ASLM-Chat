# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
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
        "call_description": "Convert reference currency",
        "web": {
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
            }
        },
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
    web_schema = schema["properties"]["web"]
    item, batch = web_schema["oneOf"]
    assert schema["required"] == ["call_description"]
    assert schema["minProperties"] == 1
    assert set(schema["properties"]) == {
        "call_description", "web", "academic", "shopping", "effort"
    }
    assert batch["maxItems"] == 2
    assert item["type"] == "string"
    assert batch["items"]["type"] == "string"
    assert "Required complete, non-empty search query" in item["description"]
    assert "Choose the query field by evidence type" in build_search_description()
    description = build_search_description()
    assert "Never submit more than two queries total" in description
    assert "High effort never\nbatches" in description

    monkeypatch.setattr(config_module, "load_search_config", lambda: _config(tor=True))
    assert "onion" in build_search_schema()["properties"]


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
    assert prepared["canonical_arguments"]["web"] == query
    assert prepared["canonical_arguments"]["call_description"] == "Convert reference currency"
    assert prepared["search_request"]["description"] == "Convert reference currency"


def test_advanced_plan_rejects_legacy_shape_and_is_atomic(monkeypatch):
    monkeypatch.setattr(config_module, "load_search_config", lambda: _config())
    rejected = prepare_search_arguments({"query": "legacy query"})
    assert rejected["ok"] is False
    assert rejected["error_result"]["error"]["code"] == "INVALID_SEARCH_PLAN"

    plan = _plan()
    plan["web"] = [plan["web"], {"text": "query site:example.com"}]
    with pytest.raises(PlanValidationError) as exc:
        prepare_advanced_search(plan, query_config=_config().query)
    assert any(issue["path"].endswith(".text") for issue in exc.value.issues)


def test_preflight_advertises_normalized_activity_description(monkeypatch):
    monkeypatch.setattr(config_module, "load_search_config", lambda: _config())

    prepared = prepare_search_arguments(_plan())

    assert prepared["arguments"]["call_description"] == "Convert reference currency"
    assert prepared["tool_ui"]["description"] == "Convert reference currency"
    assert prepared["tool_ui"]["search_request"]["description"] == "Convert reference currency"


def test_advanced_plan_requires_call_description_and_rejects_invalid_or_group():
    plan = _plan()
    del plan["call_description"]
    plan["web"]["operators"]["or_groups"] = [["only one"]]

    with pytest.raises(PlanValidationError) as exc:
        prepare_advanced_search(plan, query_config=_config().query)

    paths = {issue["path"] for issue in exc.value.issues}
    assert "$.call_description" in paths
    assert "$.web.operators.or_groups[0]" in paths


def test_advanced_plan_rejects_ambiguous_legacy_description_field():
    with pytest.raises(PlanValidationError) as exc:
        prepare_advanced_search(
            {
                "description": "Ambiguous old field",
                "web": "cve.global project capabilities",
                "effort": "medium",
            },
            query_config=_config().query,
        )

    assert {issue["path"] for issue in exc.value.issues} == {
        "$.description",
        "$.call_description",
    }


def test_advanced_plan_enforces_two_query_total_atomically():
    plan = _plan()
    plan["web"] = [plan["web"], {"text": "second web intent"}]
    plan["academic"] = {"text": "third academic intent"}

    with pytest.raises(PlanValidationError) as exc:
        prepare_advanced_search(plan, query_config=_config().query)

    assert exc.value.issues == [{
        "path": "$",
        "message": (
            "batch permits at most 2 queries total: either two in one vertical or one in "
            "each of two verticals"
        ),
    }]


def test_advanced_plan_accepts_two_queries_in_one_vertical():
    plan = {
        "call_description": "Compare web evidence",
        "web": ["web evidence one", "web evidence two"],
        "effort": "medium",
    }

    prepared = prepare_advanced_search(plan, query_config=_config().query)

    assert [q["vertical"] for q in prepared["search_request"]["queries"]] == ["web", "web"]
    assert isinstance(prepared["canonical_arguments"]["web"], list)


def test_advanced_plan_accepts_one_query_in_each_of_two_verticals():
    plan = {
        "call_description": "Compare prices and tests",
        "shopping": "Steam Deck OLED price",
        "web": "Steam Deck OLED battery test",
        "effort": "medium",
    }

    prepared = prepare_advanced_search(plan, query_config=_config().query)

    assert [q["vertical"] for q in prepared["search_request"]["queries"]] == [
        "shopping",
        "web",
    ]


def test_high_effort_executes_first_query_and_returns_batch_warning(monkeypatch):
    monkeypatch.setattr(config_module, "load_search_config", lambda: _config())
    plan = {
        "call_description": "Check critical evidence",
        "academic": ["first critical study", "second critical study"],
        "effort": "high",
    }

    prepared = prepare_search_arguments(plan)

    assert prepared["ok"] is True
    assert prepared["arguments"]["academic"] == "first critical study"
    assert len(prepared["search_request"]["queries"]) == 1
    assert prepared["search_request"]["queries"][0]["compiled_query"] == "first critical study"
    assert prepared["warnings"] == [
        {
            "code": "HIGH_EFFORT_BATCH_TRUNCATED",
            "message": (
                "High effort does not allow batching. Only the first query was executed; "
                "submit any remaining queries separately with medium or low effort."
            ),
        }
    ]
    assert prepared["tool_ui"]["warnings"] == prepared["warnings"]


def test_high_effort_warning_is_returned_to_model_after_first_query_runs(monkeypatch):
    monkeypatch.setattr(config_module, "load_search_config", lambda: _config())
    server_path = Path(__file__).resolve().parents[1] / "mcp-server.py"
    spec = importlib.util.spec_from_file_location("web_search_mcp_server_test", server_path)
    assert spec is not None and spec.loader is not None
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    captured_requests: list[dict] = []

    async def fake_run_web_search_plan(request):
        captured_requests.append(request)
        return {
            "sources": [],
            "model_context": "First-query evidence",
            "ui": {"kind": "web_search", "status": "completed"},
        }

    monkeypatch.setattr(server, "run_web_search_plan", fake_run_web_search_plan)
    monkeypatch.setattr(server, "write_search_io_event", lambda _event: None)
    raw_arguments = {
        "call_description": "Check critical evidence",
        "web": ["first query", "second query"],
        "effort": "high",
    }
    canonical_arguments = prepare_search_arguments(raw_arguments)["arguments"]
    result = asyncio.run(server.call_tool(
        "web_search",
        canonical_arguments,
        {"raw_tool_arguments": raw_arguments},
    ))

    assert len(captured_requests) == 1
    assert [query["compiled_query"] for query in captured_requests[0]["queries"]] == ["first query"]
    assert result["model_context"].startswith(
        "HIGH_EFFORT_BATCH_TRUNCATED: High effort does not allow batching."
    )
    assert result["model_context"].endswith("First-query evidence")
    assert result["ui"]["warnings"] == result["warnings"]


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
    assert calls[0][1]["vertical_only"] is False
    assert calls[1][1]["vertical_only"] is True
    assert calls[0][1]["query_text"] == "alpha"
    assert calls[0][1]["operators"] == {"after": "2026-07-01"}
    assert result["ui"]["description"] == "Compare evidence sources"
    assert result["ui"]["search_request"]["description"] == "Compare evidence sources"
    assert result["query_results"][1]["index"] == 2
    assert result["query_results"][1]["vertical"] == "shopping"
    assert result["sources"][0]["query_index"] == 1
    assert result["sources"][0]["vertical"] == "web"
    assert len({source["id"] for source in result["sources"]}) == 2
