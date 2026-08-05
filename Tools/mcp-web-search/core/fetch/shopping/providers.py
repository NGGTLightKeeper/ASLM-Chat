# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable
from urllib.parse import quote, quote_plus


@dataclass(frozen=True, slots=True)
class ShoppingProvider:
    name: str
    lane: str
    url_builder: Callable[[str], str]
    default_currency: str = ""
    methods: tuple[str, ...] = ("curl_cffi",)
    timeout_sec: float = 5.0
    cooldown_sec: float = 60.0
    failure_threshold: int = 2
    weight: float = 1.0
    notes: str = ""
    enabled: bool = True
    tags: tuple[str, ...] = field(default_factory=tuple)


def _q(query: str) -> str:
    return quote_plus(query)


def _path_q(query: str) -> str:
    return quote(query.strip(), safe="")


PROVIDERS: tuple[ShoppingProvider, ...] = (
    ShoppingProvider(
        name="pricerunner",
        lane="primary",
        url_builder=lambda query: f"https://www.pricerunner.com/results?q={_q(query)}",
        default_currency="GBP",
        methods=("httpx",),
        timeout_sec=5.0,
        cooldown_sec=180.0,
        failure_threshold=2,
        weight=1.0,
        notes="Best cold-start source in probes; httpx returned parsed content without transport fallback.",
        tags=("price_comparison", "stable"),
    ),
    ShoppingProvider(
        name="bing_shopping",
        lane="secondary",
        url_builder=lambda query: f"https://www.bing.com/shop?q={_q(query)}",
        default_currency="USD",
        methods=("curl_cffi",),
        timeout_sec=5.0,
        cooldown_sec=90.0,
        failure_threshold=3,
        weight=0.75,
        notes="Stable through curl_cffi; httpx produced no parsed products in probes.",
        tags=("aggregator", "diversity"),
    ),
    ShoppingProvider(
        name="geizhals",
        lane="secondary",
        url_builder=lambda query: f"https://geizhals.at/?fs={_q(query)}",
        default_currency="EUR",
        methods=("curl_cffi",),
        timeout_sec=5.0,
        cooldown_sec=600.0,
        failure_threshold=1,
        weight=0.55,
        notes="curl_cffi-only backup; sensitive to 403/429, so swap provider instead of retrying transport.",
        tags=("price_comparison", "sensitive"),
    ),
    ShoppingProvider(
        name="ek_ua",
        lane="secondary",
        url_builder=lambda query: f"https://ek.ua/ek-list.php?search_={_q(query)}",
        default_currency="UAH",
        methods=("curl_cffi",),
        timeout_sec=5.0,
        cooldown_sec=240.0,
        failure_threshold=2,
        weight=0.35,
        notes="curl_cffi-only weak backup; use for diversity when stronger secondary sources cool down.",
        tags=("price_comparison", "weak_parser"),
    ),
    ShoppingProvider(
        name="yandex_market",
        lane="secondary",
        url_builder=lambda query: f"https://market.yandex.ru/search?text={_q(query)}",
        default_currency="RUB",
        methods=("curl_cffi",),
        timeout_sec=8.0,
        cooldown_sec=300.0,
        failure_threshold=2,
        weight=0.45,
        notes="Russian marketplace/price source; useful for RUB offers and regional availability diversity.",
        tags=("marketplace", "russia", "regional"),
    ),
    ShoppingProvider(
        name="aliexpress",
        lane="secondary",
        url_builder=lambda query: f"https://www.aliexpress.com/wholesale?SearchText={_q(query)}",
        default_currency="USD",
        methods=("curl_cffi",),
        timeout_sec=6.0,
        cooldown_sec=240.0,
        failure_threshold=2,
        weight=0.42,
        notes="China cross-border marketplace; adds low-cost global listings outside European comparison indexes.",
        tags=("marketplace", "china", "cross_border"),
    ),
    ShoppingProvider(
        name="chinandex",
        lane="secondary",
        url_builder=lambda query: f"https://chinandex.com/s/?q={_q(query)}",
        default_currency="USD",
        methods=("curl_cffi",),
        timeout_sec=6.0,
        cooldown_sec=240.0,
        failure_threshold=2,
        weight=0.40,
        notes="China product search aggregator spanning multiple Chinese stores; generic HTML parser yields priced offers.",
        tags=("price_comparison", "china", "aggregator"),
    ),
    ShoppingProvider(
        name="kakaku",
        lane="secondary",
        url_builder=lambda query: f"https://kakaku.com/search_results/{_path_q(query)}/",
        default_currency="JPY",
        methods=("curl_cffi",),
        timeout_sec=8.0,
        cooldown_sec=420.0,
        failure_threshold=2,
        weight=0.30,
        notes="Japanese price-comparison fallback; broadens shopping coverage beyond US/EU/RU/CN sources.",
        tags=("price_comparison", "japan", "regional"),
    ),
)


PRIMARY_ROUTE_ORDER: dict[str, tuple[str, ...]] = {
    "ru": ("yandex_market", "ek_ua", "pricerunner"),
    "zh": ("chinandex", "aliexpress", "pricerunner"),
    "ja": ("kakaku", "pricerunner"),
    "en": ("pricerunner",),
}

SECONDARY_ROUTE_ORDER: dict[str, tuple[str, ...]] = {
    "ru": ("ek_ua", "chinandex", "aliexpress", "kakaku", "bing_shopping", "geizhals", "yandex_market"),
    "zh": ("aliexpress", "bing_shopping", "kakaku", "geizhals", "ek_ua", "yandex_market", "chinandex"),
    "ja": ("chinandex", "bing_shopping", "aliexpress", "geizhals", "ek_ua", "yandex_market", "kakaku"),
    "en": ("bing_shopping", "geizhals", "ek_ua", "yandex_market", "aliexpress", "chinandex", "kakaku"),
}


def _normalize_language(language: str | None) -> str:
    value = (language or "en").strip().lower()
    return value.split("-", 1)[0] or "en"


def _route_order_for_lane(lane: str, language: str | None) -> tuple[str, ...]:
    lang = _normalize_language(language)
    if lane == "primary":
        return PRIMARY_ROUTE_ORDER.get(lang, PRIMARY_ROUTE_ORDER["en"])
    if lane == "secondary":
        return SECONDARY_ROUTE_ORDER.get(lang, SECONDARY_ROUTE_ORDER["en"])
    return ()


def providers_for_lane(lane: str, *, language: str | None = None) -> list[ShoppingProvider]:
    providers = [provider for provider in PROVIDERS if provider.enabled]
    route_order = _route_order_for_lane(lane, language)
    if not route_order:
        same_lane = [provider for provider in providers if provider.lane == lane]
        return sorted(same_lane, key=lambda provider: provider.weight, reverse=True)

    by_name = {provider.name: provider for provider in providers}
    routed = [
        provider if provider.lane == lane else replace(provider, lane=lane)
        for name in route_order
        if (provider := by_name.get(name)) is not None
    ]
    routed_names = {provider.name for provider in routed}
    rest = [
        provider
        for provider in providers
        if provider.lane == lane and provider.name not in routed_names
    ]
    return routed + sorted(rest, key=lambda provider: provider.weight, reverse=True)
