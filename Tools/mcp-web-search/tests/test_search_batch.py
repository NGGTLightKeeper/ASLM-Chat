# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Offline coverage for model-facing web-search batching."""

from __future__ import annotations

import asyncio

import core.search.web_search as search_module
from core.cache.query_normalizer import has_search_operators
from core.extract.scoring import query_terms
from core.mcp_contract import (
    SEARCH_BATCH_LIMIT,
    WEB_SEARCH_TOOL_DESCRIPTION,
    build_search_schema,
    coerce_search_queries,
    coerce_search_query,
)


def test_query_schema_accepts_one_string_or_three_query_batch():
    query_schema = build_search_schema()["properties"]["query"]
    string_schema, batch_schema = query_schema["oneOf"]

    assert string_schema["type"] == "string"
    assert batch_schema["type"] == "array"
    assert batch_schema["maxItems"] == SEARCH_BATCH_LIMIT == 3
    assert batch_schema["items"]["type"] == "string"


def test_query_batch_coercion_caps_and_sanitizes_items():
    assert coerce_search_queries(["  first   query  ", "", "second", "third", "fourth"]) == [
        "first query",
        "second",
        "third",
    ]
    assert coerce_search_queries('["alpha", "beta"]') == ["alpha", "beta"]
    assert coerce_search_queries({"query": ["alpha", "beta"]}) == ["alpha", "beta"]
    assert coerce_search_query(["alpha", "beta"]) == "alpha"


def test_tool_description_documents_batch_and_operator_examples():
    assert "pass query as an array of strings" in WEB_SEARCH_TOOL_DESCRIPTION
    assert "site:reddit.com" in WEB_SEARCH_TOOL_DESCRIPTION
    assert "postgresql OR postgres" in WEB_SEARCH_TOOL_DESCRIPTION
    assert "-car -automotive" in WEB_SEARCH_TOOL_DESCRIPTION
    assert "filetype:pdf" in WEB_SEARCH_TOOL_DESCRIPTION
    assert 'intitle:"release notes"' in WEB_SEARCH_TOOL_DESCRIPTION
    assert "inurl:issues" in WEB_SEARCH_TOOL_DESCRIPTION
    assert "after:2026-01-01 before:2026-07-01" in WEB_SEARCH_TOOL_DESCRIPTION


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
