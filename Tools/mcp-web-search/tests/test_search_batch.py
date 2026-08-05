# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Offline coverage for model-facing web-search batching."""

from __future__ import annotations

import asyncio

import core.search.web_search as search_module
from core.cache.query_normalizer import has_search_operators
from core.extract.scoring import query_terms
from core.mcp_contract import (
    ADVANCED_WEB_SEARCH_TOOL_DESCRIPTION,
    LEGACY_WEB_SEARCH_TOOL_DESCRIPTION,
    LEGACY_BATCH_LIMIT,
    SEARCH_BATCH_LIMIT,
    build_search_schema,
    coerce_search_queries,
    coerce_search_query,
    prepare_search_arguments,
)


def test_legacy_query_schema_advertises_largest_vertical_batch(monkeypatch):
    import core.config as config_module

    cfg = type("Cfg", (), {
        "query": type("Query", (), {"schema_mode": "legacy"})(),
        "tor": type("Tor", (), {"enabled": False})(),
    })()
    monkeypatch.setattr(config_module, "load_search_config", lambda: cfg)
    query_schema = build_search_schema()["properties"]["query"]
    string_schema, batch_schema = query_schema["oneOf"]

    assert string_schema["type"] == "string"
    assert batch_schema["type"] == "array"
    assert SEARCH_BATCH_LIMIT == 2
    assert batch_schema["maxItems"] == LEGACY_BATCH_LIMIT == 2
    assert batch_schema["items"]["type"] == "string"
    assert "calendar years are forbidden" in query_schema["description"]


def test_query_batch_coercion_caps_and_sanitizes_items():
    assert coerce_search_queries(["  first   query  ", "", "second", "third", "fourth"]) == [
        "first query",
        "second",
    ]
    assert coerce_search_queries('["alpha", "beta"]') == ["alpha", "beta"]
    assert coerce_search_queries({"query": ["alpha", "beta"]}) == ["alpha", "beta"]
    assert coerce_search_query(["alpha", "beta"]) == "alpha"


def test_legacy_preflight_rejects_oversized_batch_instead_of_truncating(monkeypatch):
    import core.config as config_module

    cfg = type("Cfg", (), {
        "query": type("Query", (), {"schema_mode": "legacy"})(),
        "tor": type("Tor", (), {"enabled": False})(),
    })()
    monkeypatch.setattr(config_module, "load_search_config", lambda: cfg)

    prepared = prepare_search_arguments({"query": ["alpha", "beta", "gamma"]})

    assert prepared["ok"] is False
    assert prepared["error_result"]["error"]["code"] == "INVALID_SEARCH_PLAN"
    assert prepared["error_result"]["error"]["issues"] == [
        {"path": "$.query", "message": "web permits at most 2 queries per call"}
    ]


def test_legacy_preflight_caps_every_vertical_at_two_queries(monkeypatch):
    import core.config as config_module

    cfg = type("Cfg", (), {
        "query": type("Query", (), {"schema_mode": "legacy"})(),
        "tor": type("Tor", (), {"enabled": False})(),
    })()
    monkeypatch.setattr(config_module, "load_search_config", lambda: cfg)

    shopping = prepare_search_arguments({
        "query": [f"product {index}" for index in range(2)],
        "shopping": True,
    })
    academic = prepare_search_arguments({
        "query": [f"paper {index}" for index in range(2)],
        "academic": True,
    })
    too_many_shopping = prepare_search_arguments({
        "query": [f"product {index}" for index in range(3)],
        "shopping": True,
    })

    assert shopping["ok"] is True
    assert len(shopping["search_request"]["queries"]) == 2
    assert academic["ok"] is True
    assert len(academic["search_request"]["queries"]) == 2
    assert too_many_shopping["ok"] is False
    assert too_many_shopping["error_result"]["error"]["issues"] == [
        {"path": "$.query", "message": "shopping permits at most 2 queries per call"}
    ]


def test_tool_description_documents_rare_batch_and_operator_examples():
    normalized = " ".join(LEGACY_WEB_SEARCH_TOOL_DESCRIPTION.split())
    assert "make an internal plan before calling this tool" in normalized
    assert "answer deliverables, evidence gaps, source classes" in normalized
    assert "Each call executes the next plan step" in normalized
    assert "Link count alone is not coverage" in normalized
    assert "Arrays are reserved" in LEGACY_WEB_SEARCH_TOOL_DESCRIPTION
    assert "Every vertical permits\nat most 2 queries" in LEGACY_WEB_SEARCH_TOOL_DESCRIPTION
    assert "site:docs.example.com" in LEGACY_WEB_SEARCH_TOOL_DESCRIPTION
    assert "postgresql OR postgres" in LEGACY_WEB_SEARCH_TOOL_DESCRIPTION
    assert "filetype:pdf" in LEGACY_WEB_SEARCH_TOOL_DESCRIPTION
    assert 'intitle:"release notes"' in LEGACY_WEB_SEARCH_TOOL_DESCRIPTION
    assert "Date bounds fit requests" in LEGACY_WEB_SEARCH_TOOL_DESCRIPTION
    assert "four-digit calendar years" in LEGACY_WEB_SEARCH_TOOL_DESCRIPTION
    assert "exclusively inside after: or before:" in LEGACY_WEB_SEARCH_TOOL_DESCRIPTION
    assert "medium up to 10" in LEGACY_WEB_SEARCH_TOOL_DESCRIPTION
    legacy_normalized = " ".join(LEGACY_WEB_SEARCH_TOOL_DESCRIPTION.split())
    assert "shopping=true for product discovery" in legacy_normalized
    assert "academic=true for papers" in legacy_normalized
    advanced_normalized = " ".join(ADVANCED_WEB_SEARCH_TOOL_DESCRIPTION.split())
    assert "Choose the query field by evidence type" in advanced_normalized
    assert "Never submit more than two queries total" in advanced_normalized
    assert "High effort never batches" in advanced_normalized


def test_advanced_operators_are_recognized_without_polluting_scoring_terms():
    for query in (
        "report filetype:pdf",
        'pytorch intitle:"release notes"',
        "kubernetes inurl:issues",
        "pricing after:2026-01-01 before:2026-07-01",
    ):
        assert has_search_operators(query)

    assert query_terms("EU AI Act filetype:pdf after:2026-01-01") == ["act"]
    assert query_terms("pytorch intitle:release inurl:issues") == [
        "pytorch",
        "release",
        "issues",
    ]


def test_batch_runs_concurrently_and_combines_citable_sources(monkeypatch):
    active = 0
    max_active = 0

    async def fake_search(query: str, **kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {
            "query": query,
            "search_id": f"srch_{query}",
            "effort": kwargs.get("effort"),
            "language": "en",
            "region": "us-en",
            "engines_used": ["fake"],
            "cached": False,
            "model_context": f"old context for {query}",
            "sources": [
                {
                    "id": "cold-1",
                    "url": f"https://example.com/{query}",
                    "host": "example.com",
                    "title": f"Result for {query}",
                    "snippet": f"Snippet for {query}",
                    "rank": 1,
                }
            ],
        }

    monkeypatch.setattr(search_module, "run_web_search", fake_search)
    result = asyncio.run(search_module.run_web_search_batch(
        ["alpha query", "beta query"], effort="medium"
    ))

    assert max_active == 2
    assert result["batch"] is True
    assert result["queries"] == ["alpha query", "beta query"]
    assert result["ui"]["query_count"] == 2
    assert result["ui"]["status"] == "done"
    assert [source["batch_query"] for source in result["sources"]] == [
        "alpha query",
        "beta query",
    ]
    citation_ids = [source["id"] for source in result["sources"]]
    assert len(citation_ids) == len(set(citation_ids))
    assert all(f"[{citation_id}]" in result["model_context"] for citation_id in citation_ids)
    assert [entry["source_count"] for entry in result["query_results"]] == [1, 1]
