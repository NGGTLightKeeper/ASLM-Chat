# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import pytest

from core.query.routing_score import QueryClassWeight
from services.web_search import (
    _append_shopping_context,
    _build_shopping_payload,
    _shopping_intent_weight,
    _shopping_limit_for_effort,
    _shopping_source_from_product,
    _should_run_shopping_core,
)


@pytest.fixture
def product() -> dict:
    return {
        "title": "Example Phone 128 GB",
        "url": "https://example.com/p/phone",
        "source": "pricerunner",
        "source_domain": "pricerunner.com",
        "lane": "primary",
        "price_text": "$599.99",
        "price_value": 599.99,
        "currency": "USD",
        "seller": "Example Store",
        "availability": "In stock",
        "rating": "4.5",
        "review_count": 120,
        "favicon_url": "/api/favicon/?domain=pricerunner.com",
        "snippet": "Strictly parsed product card.",
        "confidence": 0.91,
    }


@pytest.mark.unit
def test_shopping_intent_uses_primary_class_as_strong_signal() -> None:
    mix = [QueryClassWeight("shopping", 0.51), QueryClassWeight("general", 0.49)]

    assert _shopping_intent_weight(mix, ["shopping", "general"]) == 1.0
    assert _should_run_shopping_core(mix, ["shopping", "general"])


@pytest.mark.unit
def test_shopping_intent_ignores_weak_secondary_signal() -> None:
    mix = [QueryClassWeight("general", 0.8), QueryClassWeight("shopping", 0.2)]

    assert not _should_run_shopping_core(mix, ["general", "shopping"])


@pytest.mark.unit
def test_shopping_effort_limits_are_smaller_on_low_effort() -> None:
    assert _shopping_limit_for_effort("low", 20) < _shopping_limit_for_effort("high", 20)
    assert _shopping_limit_for_effort("medium", 5) <= 5


@pytest.mark.unit
def test_shopping_product_becomes_citable_search_source(product: dict) -> None:
    source = _shopping_source_from_product(product, 3, "cabc-3")

    assert source is not None
    assert source.id == "cabc-3"
    assert source.rank == 3
    assert source.trust_tier == "shopping"
    assert source.engine == "shopping:pricerunner"
    assert "$599.99" in source.snippet
    assert source.favicon_url == "/api/favicon/?domain=pricerunner.com"


@pytest.mark.unit
def test_shopping_json_schema_keeps_price_and_citation_strict(product: dict) -> None:
    payload = _build_shopping_payload(
        "example phone price",
        "medium",
        {
            "products": [product],
            "mix": {"primary": 0.6, "secondary": 0.4},
            "timings": {"total_elapsed_ms": 123},
            "partial": False,
        },
        ["cabc-7"],
    )

    assert payload["schema_version"] == "shopping_search.v1"
    assert payload["parser_version"] == "strict_price.v1"
    assert payload["source_count"] == 1
    assert payload["products"][0]["citation_id"] == "cabc-7"
    assert payload["products"][0]["parse_status"] == "price_parsed"
    assert payload["products"][0]["price_value"] == 599.99
    assert payload["products"][0]["currency"] == "USD"


@pytest.mark.unit
def test_low_effort_shopping_json_omits_auxiliary_metadata(product: dict) -> None:
    payload = _build_shopping_payload("example phone price", "low", {"products": [product]}, ["cabc-1"])

    item = payload["products"][0]
    assert "snippet" not in item
    assert "rating" not in item
    assert "attempts" not in payload
    assert payload["source_count"] == 1


@pytest.mark.unit
def test_shopping_context_appends_json_block(product: dict) -> None:
    payload = _build_shopping_payload("example phone price", "medium", {"products": [product]}, ["cabc-1"])
    context = _append_shopping_context("Search results for: example phone price", payload)

    assert "Shopping structured data" in context
    assert '"citation_id":"cabc-1"' in context
    assert '"price_value":599.99' in context
