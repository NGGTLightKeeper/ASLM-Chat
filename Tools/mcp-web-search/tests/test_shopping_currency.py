# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from core.fetch.shopping.currency import (
    DEFAULT_DISPLAY_CURRENCIES,
    DISPLAY_CURRENCY_COUNT,
    RATE_CACHE_TTL_SECONDS,
    _rate_cache,
    converted_prices,
    enrich_products_with_exchange_rates,
    parse_exchange_rate_api_table,
)
from core.fetch.shopping.models import ShoppingProduct
from core.search.web_search import _shopping_product_dict


def _api_response(*, gbp_rate: float = 0.8) -> bytes:
    rates = {code: float(index + 1) for index, code in enumerate(DEFAULT_DISPLAY_CURRENCIES)}
    rates.update({"USD": 1.0, "GBP": gbp_rate, "EUR": 0.9, "ZAR": 20.0})
    return json.dumps(
        {
            "result": "success",
            "provider": "https://www.exchangerate-api.com",
            "documentation": "https://www.exchangerate-api.com/docs/free",
            "terms_of_use": "https://www.exchangerate-api.com/terms",
            "time_last_update_unix": 1785897600,
            "base_code": "USD",
            "rates": rates,
        }
    ).encode()


def test_display_currency_count_tracks_project_locale_count() -> None:
    project_root = Path(__file__).resolve().parents[3]
    locale_count = len(list((project_root / "Apps" / "UI" / "locales").glob("*.json")))
    manifest_locale_count = len(
        list((project_root / "Settings" / "module_manifest_locales").glob("*.json"))
    )

    assert locale_count == 20
    assert manifest_locale_count == locale_count
    assert DISPLAY_CURRENCY_COUNT == locale_count
    assert len(set(DEFAULT_DISPLAY_CURRENCIES)) == locale_count
    assert RATE_CACHE_TTL_SECONDS == 60 * 60


def test_public_api_rates_convert_cross_currencies() -> None:
    table = parse_exchange_rate_api_table(_api_response())

    assert table.provider == "ExchangeRate-API"
    assert table.date == "2026-08-05"
    assert float(table.rate("GBP", "USD")) == pytest.approx(1.25)
    assert float(table.rate("GBP", "EUR")) == pytest.approx(1.125)
    assert table.attribution == "Rates By Exchange Rate API"


def test_price_has_twenty_currencies_including_original() -> None:
    table = parse_exchange_rate_api_table(_api_response())
    prices = converted_prices(100, "GBP", [table])

    assert len(prices) == DISPLAY_CURRENCY_COUNT - 1
    assert len({item["currency"] for item in prices} | {"GBP"}) == DISPLAY_CURRENCY_COUNT
    usd = next(item for item in prices if item["currency"] == "USD")
    assert usd["value"] == 125.0
    assert usd["attribution_url"] == "https://www.exchangerate-api.com"


def test_unknown_primary_currency_still_uses_twenty_total_slots() -> None:
    table = parse_exchange_rate_api_table(_api_response())

    assert "ZAR" not in DEFAULT_DISPLAY_CURRENCIES
    assert len(converted_prices(100, "ZAR", [table])) == DISPLAY_CURRENCY_COUNT - 1


def test_shopping_source_json_keeps_primary_and_all_converted_prices() -> None:
    table = parse_exchange_rate_api_table(_api_response())
    product = ShoppingProduct(
        id="p1",
        title="Test product",
        url="https://shop.example/p1",
        source="shop",
        source_domain="shop.example",
        lane="primary",
        price_text="100 GBP",
        price_value=100.0,
        currency="GBP",
        converted_prices=converted_prices(100, "GBP", [table]),
    )

    source = _shopping_product_dict(product, citation_id="c1", rank=1)

    assert source["price"] == {
        "value": 100.0,
        "currency": "GBP",
        "price_text": "100 GBP",
    }
    assert source["price_value"] == 100.0
    assert source["display_currency_count"] == DISPLAY_CURRENCY_COUNT
    assert len(source["converted_prices"]) == DISPLAY_CURRENCY_COUNT - 1
    assert "125.00 USD" in source["snippet"]


def test_parallel_enrichment_fetches_one_hourly_rate_snapshot() -> None:
    requests = 0

    async def handler(request):
        nonlocal requests
        requests += 1
        return httpx.Response(200, content=_api_response(), request=request)

    async def run() -> list[ShoppingProduct]:
        _rate_cache.clear()
        products = [
            ShoppingProduct(
                id=str(index),
                title="Test product",
                url=f"https://shop.example/{index}",
                source="shop",
                source_domain="shop.example",
                lane="primary",
                price_text="100 GBP",
                price_value=100.0,
                currency="GBP",
            )
            for index in range(4)
        ]
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await asyncio.gather(
                *(enrich_products_with_exchange_rates([product], client=client) for product in products)
            )
        return products

    products = asyncio.run(run())
    assert requests == 1
    assert all(len(product.converted_prices) == DISPLAY_CURRENCY_COUNT - 1 for product in products)


def test_expired_hourly_snapshot_is_refetched_and_changes_price_math() -> None:
    requests = 0

    async def handler(request):
        nonlocal requests
        requests += 1
        gbp_rate = 0.8 if requests == 1 else 0.5
        return httpx.Response(200, content=_api_response(gbp_rate=gbp_rate), request=request)

    def product(product_id: str) -> ShoppingProduct:
        return ShoppingProduct(
            id=product_id,
            title="Test product",
            url=f"https://shop.example/{product_id}",
            source="shop",
            source_domain="shop.example",
            lane="primary",
            price_text="100 GBP",
            price_value=100.0,
            currency="GBP",
        )

    async def run() -> tuple[ShoppingProduct, ShoppingProduct, ShoppingProduct]:
        _rate_cache.clear()
        first, cached, refreshed = product("first"), product("cached"), product("refreshed")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await enrich_products_with_exchange_rates([first], client=client)
            await enrich_products_with_exchange_rates([cached], client=client)
            _, table = _rate_cache["exchange-rate-api-usd"]
            _rate_cache["exchange-rate-api-usd"] = (0.0, table)
            await enrich_products_with_exchange_rates([refreshed], client=client)
        return first, cached, refreshed

    first, cached, refreshed = asyncio.run(run())
    first_usd = next(item for item in first.converted_prices if item["currency"] == "USD")
    cached_usd = next(item for item in cached.converted_prices if item["currency"] == "USD")
    refreshed_usd = next(item for item in refreshed.converted_prices if item["currency"] == "USD")

    assert requests == 2
    assert first_usd["value"] == 125.0
    assert cached_usd["value"] == 125.0
    assert refreshed_usd["value"] == 200.0
