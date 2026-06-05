---
title: "providers"
draft: false
---

## Module `providers`

`Tools/mcp-web-search/core/fetch/shopping/providers.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/fetch/shopping`. Provider configurations and routing logic for shopping search.

---

## Classes

### `class ShoppingProvider`

---

## Public functions

#### `def providers_for_lane(lane: str, *, language: str | None=None) -> list[ShoppingProvider]`

**Purpose:** Returns the list of enabled providers for a specific lane (primary or secondary), ordered by their regional routing logic and weight.

---

## Private functions

#### `def _q(query: str) -> str`

**Purpose:** Implements `_q` in `providers.py`.

#### `def _path_q(query: str) -> str`

**Purpose:** Implements `_path_q` in `providers.py`.

#### `def _normalize_language(language: str | None) -> str`

**Purpose:** Implements `_normalize_language` in `providers.py`.

#### `def _route_order_for_lane(lane: str, language: str | None) -> tuple[str, ...]`

**Purpose:** Determines the preferred order of providers for a specific lane based on the query language.

---

## Related

- [shopping](../_index/)
