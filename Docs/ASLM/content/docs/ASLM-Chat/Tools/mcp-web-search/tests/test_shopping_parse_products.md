---
title: "test_shopping_parse_products"
draft: false
---

## Module `test_shopping_parse_products`

`Tools/mcp-web-search/tests/test_shopping_parse_products.py` — ASLM Chat Python module.

---

## Overview

Unit tests for parsing shopping products from raw HTML.

---

## Classes

*None*

---

## Public functions

#### `@pytest.mark.unit def test_parse_products_keeps_jsonld_product_with_valid_price() -> None`

**Purpose:** Implements `test_parse_products_keeps_jsonld_product_with_valid_price` in `test_shopping_parse_products.py`.

#### `@pytest.mark.unit def test_parse_products_drops_jsonld_product_without_valid_price() -> None`

**Purpose:** Implements `test_parse_products_drops_jsonld_product_without_valid_price` in `test_shopping_parse_products.py`.

#### `@pytest.mark.unit def test_parse_products_uses_first_jsonld_offer_list_item() -> None`

**Purpose:** Implements `test_parse_products_uses_first_jsonld_offer_list_item` in `test_shopping_parse_products.py`.

#### `@pytest.mark.unit def test_parse_products_drops_cards_without_price_for_all_providers() -> None`

**Purpose:** Implements `test_parse_products_drops_cards_without_price_for_all_providers` in `test_shopping_parse_products.py`.

#### `@pytest.mark.unit def test_parse_products_keeps_card_with_price() -> None`

**Purpose:** Implements `test_parse_products_keeps_card_with_price` in `test_shopping_parse_products.py`.

#### `@pytest.mark.unit def test_parse_products_drops_price_filter_facets() -> None`

**Purpose:** Implements `test_parse_products_drops_price_filter_facets` in `test_shopping_parse_products.py`.

#### `@pytest.mark.unit def test_parse_products_drops_short_anchor_when_price_is_only_nearby_context() -> None`

**Purpose:** Implements `test_parse_products_drops_short_anchor_when_price_is_only_nearby_context` in `test_shopping_parse_products.py`.

---

## Private functions

#### `def _parse(html: str)`

**Purpose:** Implements `_parse` in `test_shopping_parse_products.py`.

---

## Related

- [tests](../_index/)
