---
title: "search"
draft: false
---

## Module `search`

`Tools/mcp-web-search/core/fetch/onion/search.py` — ASLM Chat Python module.

---

## Classes

### `class OnionResult`

**Purpose:** Implements `OnionResult`.

---

## Public functions

#### `async def onion_search(query, limit, per_link_timeout, max_chars, concurrency, providers) -> list[OnionResult]`

**Purpose:** Deep onion search: locate via per-site search, then scrape+compress the top results.

---

## Private functions

#### `def _is_article_path(path) -> bool`

**Purpose:** Implements `_is_article_path`.

#### `def _extract_result_links(html, onion_base, clearnet_host, limit) -> list[str]`

**Purpose:** Implements `_extract_result_links`.

#### `def _search_url(name, query) -> tuple[str, str, str] | None`

**Purpose:** Implements `_search_url`.

#### `async def _scrape_one(url, query, provider, timeout, max_chars)`

**Purpose:** Implements `_scrape_one`.

#### `def _round_robin(pairs) -> list[tuple[str, str]]`

**Purpose:** Implements `_round_robin`.

---

## Related

- [onion/_index](../../_index/)
