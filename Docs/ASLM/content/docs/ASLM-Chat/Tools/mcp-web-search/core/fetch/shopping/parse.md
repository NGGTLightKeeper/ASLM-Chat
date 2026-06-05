---
title: "parse"
draft: false
---

## Module `parse`

`Tools/mcp-web-search/core/fetch/shopping/parse.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/fetch/shopping`. Parsing logic for shopping product extraction from HTML.

---

## Classes

*None*

---

## Public functions

#### `def compact(text: str, *, limit: int=260) -> str`

**Purpose:** Implements `compact` in `parse.py`.

#### `def source_domain(url: str) -> str`

**Purpose:** Implements `source_domain` in `parse.py`.

#### `def normalize_url(raw: str, base: str='') -> str`

**Purpose:** Implements `normalize_url` in `parse.py`.

#### `def parse_price(text: str, *, default_currency: str='', allow_bare: bool=False) -> tuple[str, float | None, str]`

**Purpose:** Extracts a numeric price and currency string from a given text, respecting default currencies and rejecting false positives (like ratings).

#### `def parse_amount_value(raw: str) -> float | None`

**Purpose:** Parses a localized number string into a precise float value.

#### `def product_id(url: str, title: str, source: str) -> str`

**Purpose:** Implements `product_id` in `parse.py`.

#### `def score_product(product: ShoppingProduct) -> float`

**Purpose:** Implements `score_product` in `parse.py`.

#### `def parse_products(html_text: str, *, provider: str, lane: str, method: str, base_url: str, default_currency: str='') -> list[ShoppingProduct]`

**Purpose:** Implements `parse_products` in `parse.py`.

---

## Private functions

#### `def _bare_integer_before_spaced_currency(raw: str) -> bool`

**Purpose:** Implements `_bare_integer_before_spaced_currency` in `parse.py`.

#### `def _looks_like_rating_ruble_false_positive(match: re.Match[str], source: str, amount: float) -> bool`

**Purpose:** Detects and rejects cases where a product rating is falsely identified as a Russian Ruble price.

#### `def _valid_grouped_integer(groups: list[str]) -> bool`

**Purpose:** Implements `_valid_grouped_integer` in `parse.py`.

#### `def _make_product(*, title: str, url: str, provider: str, lane: str, method: str, price_text: str='', price_value: float | None=None, currency: str='', snippet: str='', seller: str='', availability: str='') -> ShoppingProduct`

**Purpose:** Implements `_make_product` in `parse.py`.

#### `def _jsonld_products(soup: BeautifulSoup, *, provider: str, lane: str, method: str, base_url: str, default_currency: str) -> list[ShoppingProduct]`

**Purpose:** Implements `_jsonld_products` in `parse.py`.

#### `def _first_offer(raw: object) -> dict`

**Purpose:** Implements `_first_offer` in `parse.py`.

#### `def _card_products(soup: BeautifulSoup, *, provider: str, lane: str, method: str, base_url: str, default_currency: str) -> list[ShoppingProduct]`

**Purpose:** Implements `_card_products` in `parse.py`.

#### `def _looks_like_price_filter_title(title: str) -> bool`

**Purpose:** Rejects titles that look like price filter facets (e.g. 'Under 10$').

#### `def _has_enough_product_title_signal(title: str) -> bool`

**Purpose:** Ensures the title has enough text to be a valid product name, dropping short generic anchors.

#### `def _dedupe(products: list[ShoppingProduct]) -> list[ShoppingProduct]`

**Purpose:** Implements `_dedupe` in `parse.py`.

---

## Related

- [shopping](../_index/)
