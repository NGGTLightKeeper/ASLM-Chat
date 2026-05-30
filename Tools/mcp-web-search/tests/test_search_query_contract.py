# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import pytest

from adapters.mcp.search_query_contract import (
    SEARCH_QUERY_SCHEMA,
    coerce_search_effort,
    coerce_search_query,
    sanitize_legacy_query,
)


@pytest.mark.unit
def test_search_query_schema_requires_query_and_allows_effort() -> None:
    props = SEARCH_QUERY_SCHEMA["properties"]
    assert SEARCH_QUERY_SCHEMA["required"] == ["query"]
    assert props["effort"]["enum"] == ["low", "medium", "high"]
    assert props["effort"]["default"] == "medium"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  foo   bar  ", "foo bar"),
        ({"query": "nested"}, "nested"),
        ('{"query": "from json"}', "from json"),
        ({"raw_query": "legacy raw"}, "legacy raw"),
        ("", ""),
    ],
)
def test_coerce_search_query(raw: object, expected: str) -> None:
    assert coerce_search_query(raw) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, "medium"),
        ("", "medium"),
        ("high", "high"),
        ("normal", "medium"),
        ("bogus", "medium"),
        ({"effort": "low"}, "low"),
    ],
)
def test_coerce_search_effort(raw: object, expected: str) -> None:
    assert coerce_search_effort(raw) == expected


@pytest.mark.unit
def test_sanitize_legacy_query_caps_length_and_collapses_whitespace() -> None:
    long = "word " * 80
    sanitized = sanitize_legacy_query(long)
    assert len(sanitized) <= 220
    assert "\n" not in sanitized
    assert "  " not in sanitized
