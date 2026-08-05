# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ShoppingProduct:
    id: str
    title: str
    url: str
    source: str
    source_domain: str
    lane: str
    price_text: str = ""
    price_value: float | None = None
    currency: str = ""
    converted_prices: list[dict[str, Any]] = field(default_factory=list)
    seller: str = ""
    availability: str = ""
    rating: str = ""
    review_count: int | None = None
    favicon_url: str = ""
    snippet: str = ""
    confidence: float = 0.0
    fetched_at: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ShoppingProviderAttempt:
    provider: str
    lane: str
    method: str
    url: str
    ok: bool
    elapsed_ms: int
    status_code: int | None = None
    bytes: int = 0
    products: int = 0
    parse_elapsed_ms: int = 0
    error: str = ""
    cooldown_sec: float = 0.0


@dataclass(slots=True)
class ShoppingSearchResult:
    query: str
    effort: str
    primary_ratio: float
    secondary_ratio: float
    products: list[ShoppingProduct]
    attempts: list[ShoppingProviderAttempt]
    provider_state: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, Any] = field(default_factory=dict)
    exchange_rates: dict[str, Any] = field(default_factory=dict)
    partial: bool = False
    partial_reason: str = ""
