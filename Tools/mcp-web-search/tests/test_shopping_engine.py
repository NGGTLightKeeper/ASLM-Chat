# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import time

import pytest

from core.fetch.shopping.assets import ShoppingAssetCache
from core.fetch.shopping.engine import ShoppingSearchEngine, result_to_jsonable
from core.fetch.shopping.models import ShoppingProviderAttempt
from core.fetch.shopping.providers import PROVIDERS, providers_for_lane


# Shopping now uses a process-wide ProviderState; reset it before each test so a cooldown
# tripped in one test cannot leak into another's provider selection.
@pytest.fixture(autouse=True)
def _reset_shopping_state():
    from core.fetch.shopping.engine import _GLOBAL_PROVIDER_STATE

    _GLOBAL_PROVIDER_STATE.failures.clear()
    _GLOBAL_PROVIDER_STATE.cooldown_until.clear()
    _GLOBAL_PROVIDER_STATE.last_status.clear()
    yield


def _html(provider: str, count: int, *, currency: str = "$") -> str:
    cards = []
    for idx in range(count):
        cards.append(
            f'<div class="card"><a href="https://{provider}.example/p/{idx}">'
            f"{provider} product {idx} {currency}{idx + 10}.99</a>"
            f'<img src="https://img.example/{provider}-{idx}.jpg"></div>'
        )
    return "<html><body>" + "".join(cards) + "</body></html>"


@pytest.mark.unit
def test_shopping_engine_medium_effort_mixes_primary_secondary_60_40(monkeypatch) -> None:
    engine = ShoppingSearchEngine(asset_cache=ShoppingAssetCache())

    async def fake_fetch(url, provider, method):
        html = _html(provider.name, 20)
        return html, ShoppingProviderAttempt(
            provider=provider.name,
            lane=provider.lane,
            method=method,
            url=url,
            ok=True,
            elapsed_ms=1,
            status_code=200,
            bytes=len(html),
        )

    monkeypatch.setattr(engine, "_fetch", fake_fetch)

    result = asyncio_run(engine.search("iphone price", effort="medium", limit=10))

    assert len(result.products) == 10
    assert sum(1 for product in result.products if product.lane == "primary") == 6
    assert sum(1 for product in result.products if product.lane == "secondary") == 4
    assert result.primary_ratio == 0.60
    assert result.secondary_ratio == 0.40
    assert result.timings["total_elapsed_ms"] >= 0
    assert result.timings["fetch_elapsed_ms"] >= 0
    assert result.timings["parse_elapsed_ms"] >= 0
    assert all(attempt.parse_elapsed_ms >= 0 for attempt in result.attempts)


@pytest.mark.unit
def test_shopping_engine_hot_swaps_secondary_after_failures(monkeypatch) -> None:
    engine = ShoppingSearchEngine(asset_cache=ShoppingAssetCache())

    async def fake_fetch(url, provider, method):
        if provider.name == "pricerunner":
            status = 200
            html = _html(provider.name, 20)
        elif provider.name == "bing_shopping":
            status = 202
            html = ""
        elif provider.name == "geizhals":
            status = 429
            html = ""
        else:
            status = 200
            html = _html(provider.name, 20, currency="₴")
        return html, ShoppingProviderAttempt(
            provider=provider.name,
            lane=provider.lane,
            method=method,
            url=url,
            ok=bool(html) and 200 <= status < 300,
            elapsed_ms=1,
            status_code=status,
            bytes=len(html),
        )

    monkeypatch.setattr(engine, "_fetch", fake_fetch)

    result = asyncio_run(engine.search("rtx 5070 price", effort="medium", limit=10))

    secondary_sources = {product.source for product in result.products if product.lane == "secondary"}
    attempted = [attempt.provider for attempt in result.attempts]
    assert "bing_shopping" in attempted
    assert "geizhals" in attempted
    assert "ek_ua" in attempted
    assert secondary_sources == {"ek_ua"}
    assert "geizhals" in result.provider_state["cooldowns"]


@pytest.mark.unit
def test_shopping_engine_backfills_primary_shortfall_from_secondary(monkeypatch) -> None:
    engine = ShoppingSearchEngine(asset_cache=ShoppingAssetCache())

    async def fake_fetch(url, provider, method):
        if provider.name == "pricerunner":
            html = ""
            return html, ShoppingProviderAttempt(
                provider=provider.name,
                lane=provider.lane,
                method=method,
                url=url,
                ok=False,
                elapsed_ms=5,
                error="timeout",
            )
        html = _html(provider.name, 20)
        return html, ShoppingProviderAttempt(
            provider=provider.name,
            lane=provider.lane,
            method=method,
            url=url,
            ok=True,
            elapsed_ms=1,
            status_code=200,
            bytes=len(html),
        )

    monkeypatch.setattr(engine, "_fetch", fake_fetch)

    result = asyncio_run(engine.search("rtx 5070 price", effort="medium", limit=10))

    assert len(result.products) == 10
    assert {product.source for product in result.products} == {"bing_shopping"}
    assert result.timings["primary_shortfall"] == 6
    assert result.timings["secondary_fetch_limit"] == 10


@pytest.mark.unit
def test_shopping_engine_runs_primary_and_secondary_concurrently(monkeypatch) -> None:
    engine = ShoppingSearchEngine(asset_cache=ShoppingAssetCache())

    async def fake_fetch(url, provider, method):
        await asyncio.sleep(0.05)
        html = _html(provider.name, 20)
        return html, ShoppingProviderAttempt(
            provider=provider.name,
            lane=provider.lane,
            method=method,
            url=url,
            ok=True,
            elapsed_ms=50,
            status_code=200,
            bytes=len(html),
        )

    monkeypatch.setattr(engine, "_fetch", fake_fetch)

    started = time.perf_counter()
    result = asyncio_run(engine.search("iphone price", effort="medium", limit=10, hard_timeout_ms=1000))
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    assert len(result.products) == 10
    assert elapsed_ms < 140
    assert result.timings["primary_lane_elapsed_ms"] >= 50
    assert result.timings["secondary_lane_elapsed_ms"] >= 50


@pytest.mark.unit
def test_shopping_engine_returns_partial_buffer_on_hard_timeout(monkeypatch) -> None:
    engine = ShoppingSearchEngine(asset_cache=ShoppingAssetCache())

    async def fake_fetch(url, provider, method):
        if provider.lane == "primary":
            await asyncio.sleep(0.2)
            html = _html(provider.name, 20)
        else:
            await asyncio.sleep(0.01)
            html = _html(provider.name, 20)
        return html, ShoppingProviderAttempt(
            provider=provider.name,
            lane=provider.lane,
            method=method,
            url=url,
            ok=True,
            elapsed_ms=10,
            status_code=200,
            bytes=len(html),
        )

    monkeypatch.setattr(engine, "_fetch", fake_fetch)

    result = asyncio_run(engine.search("iphone price", effort="medium", limit=10, hard_timeout_ms=80))

    assert result.partial is True
    assert result.partial_reason in {"buffer_full", "hard_timeout"}
    assert len(result.products) == 10
    assert {product.lane for product in result.products} == {"secondary"}


@pytest.mark.unit
def test_shopping_engine_partial_primary_buffer_is_not_cut_to_primary_quota(monkeypatch) -> None:
    engine = ShoppingSearchEngine(asset_cache=ShoppingAssetCache())

    async def fake_fetch(url, provider, method):
        if provider.lane == "secondary":
            await asyncio.sleep(0.2)
        else:
            await asyncio.sleep(0.01)
        html = _html(provider.name, 20)
        return html, ShoppingProviderAttempt(
            provider=provider.name,
            lane=provider.lane,
            method=method,
            url=url,
            ok=True,
            elapsed_ms=10,
            status_code=200,
            bytes=len(html),
        )

    monkeypatch.setattr(engine, "_fetch", fake_fetch)

    result = asyncio_run(engine.search("iphone price", effort="medium", limit=10, hard_timeout_ms=80))

    assert result.partial is True
    assert result.partial_reason in {"buffer_full", "hard_timeout"}
    assert len(result.products) == 10
    assert {product.lane for product in result.products} == {"primary"}


@pytest.mark.unit
def test_shopping_engine_skips_provider_already_in_cooldown(monkeypatch) -> None:
    from core.fetch.shopping.engine import ProviderState

    engine = ShoppingSearchEngine(asset_cache=ShoppingAssetCache(), state=ProviderState())
    engine.state.cooldown_until["bing_shopping"] = time.time() + 60

    async def fake_fetch(url, provider, method):
        html = _html(provider.name, 20)
        return html, ShoppingProviderAttempt(
            provider=provider.name,
            lane=provider.lane,
            method=method,
            url=url,
            ok=True,
            elapsed_ms=1,
            status_code=200,
            bytes=len(html),
        )

    monkeypatch.setattr(engine, "_fetch", fake_fetch)

    result = asyncio_run(engine.search("camera price", effort="medium", limit=10))

    secondary_sources = {product.source for product in result.products if product.lane == "secondary"}
    assert "bing_shopping" not in secondary_sources
    assert secondary_sources == {"geizhals"}


@pytest.mark.unit
def test_shopping_provider_router_prefers_russian_sources_for_ru() -> None:
    primary = [provider.name for provider in providers_for_lane("primary", language="ru")]
    secondary = [provider.name for provider in providers_for_lane("secondary", language="ru")]

    assert primary[:2] == ["yandex_market", "ek_ua"]
    assert secondary[:4] == ["ek_ua", "chinandex", "aliexpress", "kakaku"]


@pytest.mark.unit
def test_shopping_provider_router_prefers_chinese_aggregator_for_zh() -> None:
    primary = [provider.name for provider in providers_for_lane("primary", language="zh")]
    secondary = [provider.name for provider in providers_for_lane("secondary", language="zh")]

    assert primary[:2] == ["chinandex", "aliexpress"]
    assert secondary[:3] == ["aliexpress", "bing_shopping", "kakaku"]


@pytest.mark.unit
def test_shopping_provider_router_prefers_japanese_aggregator_for_ja() -> None:
    primary = [provider.name for provider in providers_for_lane("primary", language="ja")]
    secondary = [provider.name for provider in providers_for_lane("secondary", language="ja")]

    assert primary[:2] == ["kakaku", "pricerunner"]
    assert secondary[:2] == ["chinandex", "bing_shopping"]


@pytest.mark.unit
def test_shopping_engine_passes_language_to_routes(monkeypatch) -> None:
    engine = ShoppingSearchEngine(asset_cache=ShoppingAssetCache())
    attempted: list[str] = []

    async def fake_fetch(url, provider, method):
        attempted.append(provider.name)
        html = "" if provider.name == "yandex_market" else _html(provider.name, 20)
        return html, ShoppingProviderAttempt(
            provider=provider.name,
            lane=provider.lane,
            method=method,
            url=url,
            ok=bool(html),
            elapsed_ms=1,
            status_code=200 if html else 204,
            bytes=len(html),
        )

    monkeypatch.setattr(engine, "_fetch", fake_fetch)

    products, _attempts = asyncio_run(engine._lane("купить iphone", "primary", limit=4, language="ru"))

    assert products
    assert "yandex_market" in attempted
    assert attempted.index("yandex_market") < attempted.index("ek_ua")


@pytest.mark.unit
def test_shopping_engine_waits_for_regional_primary_before_secondary_early_return(monkeypatch) -> None:
    engine = ShoppingSearchEngine(asset_cache=ShoppingAssetCache())

    async def fake_fetch(url, provider, method):
        if provider.name == "yandex_market":
            await asyncio.sleep(0.05)
            html = _html(provider.name, 20, currency="₽")
        elif provider.lane == "secondary":
            html = _html(provider.name, 20)
        else:
            html = ""
        return html, ShoppingProviderAttempt(
            provider=provider.name,
            lane=provider.lane,
            method=method,
            url=url,
            ok=bool(html),
            elapsed_ms=1,
            status_code=200 if html else 204,
            bytes=len(html),
        )

    monkeypatch.setattr(engine, "_fetch", fake_fetch)

    result = asyncio_run(engine.search("защитное стекло дешево", effort="medium", limit=6, language="ru"))

    assert any(product.source == "yandex_market" for product in result.products)


@pytest.mark.unit
def test_shopping_engine_uses_longer_hard_timeout_for_regional_routes() -> None:
    engine = ShoppingSearchEngine(asset_cache=ShoppingAssetCache())

    assert engine._hard_timeout_for_effort("medium", "ru") > engine._hard_timeout_for_effort("medium", "en")


@pytest.mark.unit
def test_shopping_engine_sets_favicon_proxy_without_fetching_favicon(monkeypatch) -> None:
    engine = ShoppingSearchEngine(asset_cache=ShoppingAssetCache())

    async def fake_fetch(url, provider, method):
        html = _html(provider.name, 20)
        return html, ShoppingProviderAttempt(
            provider=provider.name,
            lane=provider.lane,
            method=method,
            url=url,
            ok=True,
            elapsed_ms=1,
            status_code=200,
            bytes=len(html),
        )

    monkeypatch.setattr(engine, "_fetch", fake_fetch)

    result = asyncio_run(engine.search("iphone price", effort="low", limit=4))

    assert result.products
    assert all(product.favicon_url for product in result.products)
    assert all(product.favicon_url.startswith("/api/favicon/?domain=") for product in result.products)
    assert all(not hasattr(product, "favicon_cache_url") for product in result.products)


@pytest.mark.unit
def test_shopping_providers_use_probe_selected_single_transport() -> None:
    methods = {provider.name: provider.methods for provider in PROVIDERS}

    assert methods == {
        "pricerunner": ("httpx",),
        "bing_shopping": ("curl_cffi",),
        "geizhals": ("curl_cffi",),
        "ek_ua": ("curl_cffi",),
        "yandex_market": ("curl_cffi",),
        "aliexpress": ("curl_cffi",),
        "chinandex": ("curl_cffi",),
        "kakaku": ("curl_cffi",),
    }


@pytest.mark.unit
def test_shopping_result_json_includes_timings(monkeypatch) -> None:
    engine = ShoppingSearchEngine(asset_cache=ShoppingAssetCache())

    async def fake_fetch(url, provider, method):
        html = _html(provider.name, 20)
        return html, ShoppingProviderAttempt(
            provider=provider.name,
            lane=provider.lane,
            method=method,
            url=url,
            ok=True,
            elapsed_ms=7,
            status_code=200,
            bytes=len(html),
        )

    monkeypatch.setattr(engine, "_fetch", fake_fetch)

    payload = result_to_jsonable(asyncio_run(engine.search("iphone price", effort="low", limit=4)))

    assert payload["timings"]["total_elapsed_ms"] >= 0
    assert payload["timings"]["fetch_elapsed_ms"] >= 7
    assert "parse_elapsed_ms" in payload["attempts"][0]


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
