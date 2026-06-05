---
title: "engine"
draft: false
---

## Module `engine`

`Tools/mcp-web-search/core/fetch/shopping/engine.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/fetch/shopping`. Core logic for the shopping search engine.

---

## Classes

### `class ProviderState`

#### `def __init__(self) -> None`

**Purpose:** Initializes the provider state, including cooldown tracking and attempt history.

#### `def available(self, provider: ShoppingProvider) -> bool`

**Purpose:** Checks if a provider is currently available (not in cooldown).

#### `def record(self, provider: ShoppingProvider, attempt: ShoppingProviderAttempt, product_count: int) -> None`

**Purpose:** Records an attempt for a provider, potentially placing it in cooldown if it fails or returns empty.

#### `def snapshot(self) -> dict[str, Any]`

**Purpose:** Implements `snapshot` in `ProviderState`.

### `class ShoppingSearchEngine`

#### `def __init__(self, *, asset_cache: ShoppingAssetCache | None=None) -> None`

**Purpose:** Implements `__init__` in `ShoppingSearchEngine`.

#### `async def search(self, query: str, *, effort: str='medium', limit: int=12, language: str='en', hard_timeout_ms: int | None=None) -> ShoppingSearchResult`

**Purpose:** Main entry point for a shopping search. Manages lanes, limits, timeouts, and regional specifics.

#### `def _hard_timeout_for_effort(self, effort: str, language: str) -> int`

**Purpose:** Calculates the hard timeout for a given effort and language, allowing regional searches more time.

#### `async def _timed_lane(self, query: str, lane: str, limit: int, *, language: str='en') -> tuple[list[ShoppingProduct], list[ShoppingProviderAttempt], int]`

**Purpose:** Implements `_timed_lane` in `ShoppingSearchEngine`.

#### `async def _timed_secondary_lane(self, query: str, limit: int, *, language: str='en') -> tuple[list[ShoppingProduct], list[ShoppingProviderAttempt], int]`

**Purpose:** Implements `_timed_secondary_lane` in `ShoppingSearchEngine`.

#### `def _buffer_can_fill_limit(self, buffer: '_SearchBuffer', primary_limit: int, secondary_limit: int, total_limit: int) -> bool`

**Purpose:** Implements `_buffer_can_fill_limit` in `ShoppingSearchEngine`.

#### `def _should_wait_for_regional_primary(self, language: str, pending: set[asyncio.Task], tasks: dict[asyncio.Task, str], buffer: '_SearchBuffer') -> bool`

**Purpose:** Determines if the secondary lane should wait for regional primary providers to finish before returning.

#### `async def _lane(self, query: str, lane: str, limit: int, *, language: str='en') -> tuple[list[ShoppingProduct], list[ShoppingProviderAttempt]]`

**Purpose:** Implements `_lane` in `ShoppingSearchEngine`.

#### `async def _secondary_lane(self, query: str, limit: int, *, language: str='en') -> tuple[list[ShoppingProduct], list[ShoppingProviderAttempt]]`

**Purpose:** Implements `_secondary_lane` in `ShoppingSearchEngine`.

#### `def _ranked_available(self, lane: str, *, language: str='en') -> list[ShoppingProvider]`

**Purpose:** Implements `_ranked_available` in `ShoppingSearchEngine`.

#### `async def _provider(self, query: str, provider: ShoppingProvider) -> tuple[list[ShoppingProduct], list[ShoppingProviderAttempt]]`

**Purpose:** Implements `_provider` in `ShoppingSearchEngine`.

#### `async def _fetch(self, url: str, provider: ShoppingProvider, method: str) -> tuple[str, ShoppingProviderAttempt]`

**Purpose:** Implements `_fetch` in `ShoppingSearchEngine`.

#### `async def _fetch_httpx(self, url: str, timeout_sec: float) -> tuple[int, str]`

**Purpose:** Implements `_fetch_httpx` in `ShoppingSearchEngine`.

#### `def _fetch_curl_cffi(self, url: str, timeout_sec: float) -> tuple[int, str]`

**Purpose:** Fetches HTML content using curl_cffi for providers requiring advanced TLS fingerprinting.

#### `def _merge_products(self, primary: list[ShoppingProduct], secondary: list[ShoppingProduct], primary_limit: int, secondary_limit: int, total_limit: int) -> list[ShoppingProduct]`

**Purpose:** Implements `_merge_products` in `ShoppingSearchEngine`.

#### `def _timed_merge(self, primary: list[ShoppingProduct], secondary: list[ShoppingProduct], primary_limit: int, secondary_limit: int, total_limit: int) -> tuple[list[ShoppingProduct], int]`

**Purpose:** Implements `_timed_merge` in `ShoppingSearchEngine`.

#### `def _timed_attach_favicons(self, products: list[ShoppingProduct]) -> int`

**Purpose:** Implements `_timed_attach_favicons` in `ShoppingSearchEngine`.

#### `def _dedupe_products(self, products: list[ShoppingProduct]) -> list[ShoppingProduct]`

**Purpose:** Implements `_dedupe_products` in `ShoppingSearchEngine`.

#### `def _attach_favicons(self, products: list[ShoppingProduct]) -> None`

**Purpose:** Implements `_attach_favicons` in `ShoppingSearchEngine`.

### `class _SearchBuffer`

#### `def __init__(self) -> None`

**Purpose:** Implements `__init__` in `_SearchBuffer`.

#### `def update(self, lane: str, products: list[ShoppingProduct], attempts: list[ShoppingProviderAttempt], elapsed_ms: int) -> None`

**Purpose:** Implements `update` in `_SearchBuffer`.

---

## Public functions

#### `async def search_shopping(query: str, *, effort: str='medium', limit: int=12, language: str='en') -> ShoppingSearchResult`

**Purpose:** Implements `search_shopping` in `engine.py`.

#### `def result_to_jsonable(result: ShoppingSearchResult) -> dict[str, Any]`

**Purpose:** Implements `result_to_jsonable` in `engine.py`.

---

## Private functions

*None*

---

## Related

- [shopping](../_index/)
