# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import quote_plus


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
)


def providers_for_lane(lane: str) -> list[ShoppingProvider]:
    return [provider for provider in PROVIDERS if provider.enabled and provider.lane == lane]
