# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import core.config as config_module
import core.search.web_search as search_module
from core.mcp_contract import build_search_description, build_search_schema, prepare_search_arguments
from core.query.operators import WEB_QUERY_OPERATOR_FORMS
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
    assert schema["required"] == ["description"]
    assert schema["properties"]["description"]["maxLength"] == 80
    assert set(schema["properties"]) == {"description", "web", "shopping", "academic", "effort"}
    assert all(schema["properties"][key]["type"] == "string" for key in ("web", "shopping", "academic"))
    assert "operators are silently stripped" in schema["properties"]["shopping"]["description"]
    assert "maximally dry scholarly" in schema["properties"]["academic"]["description"]
    web_description = schema["properties"]["web"]["description"]
    assert all(operator in web_description for operator in WEB_QUERY_OPERATOR_FORMS)
    assert "Use plain terms by default" in web_description
    assert "known ambiguity" in web_description
    assert "Do not stack decorative operators" in web_description
    assert "query" not in schema["properties"]
    assert {"required": ["web"]} in schema["anyOf"]
    assert {"required": ["shopping"]} in schema["anyOf"]
    description = build_search_description()
    assert "Supply at least one vertical argument" in " ".join(description.split())
    assert len(description) < 250

    monkeypatch.setattr(config_module, "load_search_config", lambda: _config(tor=True))
    assert build_search_schema()["properties"]["onion"]["type"] == "string"


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

    prepared = prepare_search_arguments({
        "description": "Convert reference currency",
        "web": "RUB USD exchange rate site:cbr.ru",
        "shopping": "\"MacBook Air\" OR laptop site:shop.example -used",
        "academic": "\"Attention Is All You Need\" site:arxiv.org",
        "effort": "medium",
    })

    assert prepared["arguments"]["description"] == "Convert reference currency"
    assert prepared["arguments"]["web"] == "RUB USD exchange rate site:cbr.ru"
    assert prepared["arguments"]["shopping"] == "MacBook Air laptop"
    assert prepared["arguments"]["academic"] == "Attention Is All You Need"
    assert [item["vertical"] for item in prepared["search_request"]["queries"]] == [
        "web", "shopping", "academic",
    ]
    assert prepared["search_request"]["batch_kind"] == "none"
    assert prepared["tool_ui"]["description"] == "Convert reference currency"
    assert prepared["tool_ui"]["search_request"]["description"] == "Convert reference currency"


def test_advanced_preflight_accepts_specialized_vertical_without_web(monkeypatch):
    monkeypatch.setattr(config_module, "load_search_config", lambda: _config())

    prepared = prepare_search_arguments({
        "description": "Ищу цену товара",
        "shopping": "ThinkPad X1 Carbon Gen 14",
        "effort": "medium",
    })

    assert prepared["ok"] is True
    assert prepared["search_request"]["queries"][0]["vertical"] == "shopping"


def test_mixed_vertical_operators_are_stripped_locally_without_rejection(monkeypatch):
    monkeypatch.setattr(config_module, "load_search_config", lambda: _config(tor=True))
    web = 'runtime error site:docs.example.com after:2026-01-01 -deprecated'

    prepared = prepare_search_arguments({
        "description": "Проверяю разные источники",
        "web": web,
        "shopping": 'ThinkPad X1 site:shop.example -used',
        "academic": 'retrieval augmented generation site:arxiv.org after:2025-01-01',
        "onion": 'SecureDrop site:example.onion OR mirror',
        "effort": "medium",
    })

    assert prepared["ok"] is True
    assert prepared["arguments"]["web"] == web
    assert prepared["arguments"]["shopping"] == "ThinkPad X1"
    assert prepared["arguments"]["academic"] == "retrieval augmented generation"
    assert prepared["arguments"]["onion"] == "SecureDrop mirror"


def test_operator_only_specialized_vertical_is_omitted_from_valid_mixed_call(monkeypatch):
    monkeypatch.setattr(config_module, "load_search_config", lambda: _config())

    prepared = prepare_search_arguments({
        "description": "Проверяю официальный источник",
        "web": "runtime documentation site:example.com",
        "shopping": "site:shop.example -used",
        "academic": "after:2025-01-01 site:arxiv.org",
        "effort": "medium",
    })

    assert prepared["ok"] is True
    assert prepared["arguments"]["web"] == "runtime documentation site:example.com"
    assert "shopping" not in prepared["arguments"]
    assert "academic" not in prepared["arguments"]
    assert [query["vertical"] for query in prepared["search_request"]["queries"]] == ["web"]


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
        "schema_mode": "verticals",
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
    assert result["batch"] is False
    assert result["parallel_verticals"] is True
    assert result["query_results"][1]["index"] == 2
    assert result["query_results"][1]["vertical"] == "shopping"
    assert result["sources"][0]["query_index"] == 1
    assert result["sources"][0]["vertical"] == "web"
    assert len({source["id"] for source in result["sources"]}) == 2
