# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json

import pytest

from core.fetch.shopping.parse import parse_products


def _parse(html: str):
    return parse_products(
        html,
        provider="pricerunner",
        lane="primary",
        method="httpx",
        base_url="https://www.pricerunner.com/results?q=test",
        default_currency="GBP",
    )


@pytest.mark.unit
def test_parse_products_keeps_jsonld_product_with_valid_price() -> None:
    payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Stable Product",
        "url": "https://example.com/p/1",
        "offers": {
            "@type": "Offer",
            "price": "123.45",
            "priceCurrency": "GBP",
        },
    }

    products = _parse(f'<script type="application/ld+json">{json.dumps(payload)}</script>')

    assert len(products) == 1
    assert products[0].price_value == pytest.approx(123.45)
    assert products[0].currency == "GBP"


@pytest.mark.unit
def test_parse_products_drops_jsonld_product_without_valid_price() -> None:
    payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "No Price Product",
        "url": "https://example.com/p/1",
        "offers": {"priceCurrency": "GBP"},
    }

    products = _parse(f'<script type="application/ld+json">{json.dumps(payload)}</script>')

    assert products == []


@pytest.mark.unit
def test_parse_products_uses_first_jsonld_offer_list_item() -> None:
    payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Offer List Product",
        "url": "https://example.com/p/1",
        "offers": [
            {"price": "199.99", "priceCurrency": "GBP"},
            {"price": "299.99", "priceCurrency": "GBP"},
        ],
    }

    products = _parse(f'<script type="application/ld+json">{json.dumps(payload)}</script>')

    assert len(products) == 1
    assert products[0].price_value == pytest.approx(199.99)


@pytest.mark.unit
def test_parse_products_drops_cards_without_price_for_all_providers() -> None:
    html = '<a href="https://ek.example/p/1">Product without a price</a>'

    products = parse_products(
        html,
        provider="ek_ua",
        lane="secondary",
        method="curl_cffi",
        base_url="https://ek.ua/ek-list.php?search_=test",
        default_currency="UAH",
    )

    assert products == []


@pytest.mark.unit
def test_parse_products_keeps_card_with_price() -> None:
    html = (
        '<div class="card">'
        '<a href="https://example.com/p/1">Card Product £123.45</a>'
        '<img src="https://example.com/p/1.jpg">'
        '</div>'
    )

    products = _parse(html)

    assert len(products) == 1
    assert products[0].price_value == pytest.approx(123.45)
    assert products[0].currency == "GBP"
    assert not hasattr(products[0], "image_url")
