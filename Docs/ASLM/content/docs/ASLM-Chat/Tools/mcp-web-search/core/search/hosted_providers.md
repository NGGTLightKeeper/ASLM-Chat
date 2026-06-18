---
title: "hosted_providers"
draft: false
---

## Module `hosted_providers`

`Tools/mcp-web-search/core/search/hosted_providers.py` — ASLM Chat Python module.

---

## Classes

### `class HostedResult`

**Purpose:** One hosted result row. `content` is non-empty only for content-bearing providers.

### `class HostedProvider`

**Purpose:** Protocol for hosted search providers.

### `class TavilyClient`

**Purpose:** Tavily/Firecrawl "advanced" crawl returns full page text.

### `class FirecrawlClient`

**Purpose:** Client for Firecrawl API.

### `class BraveClient`

**Purpose:** Client for Brave Search API.

### `class SerpApiClient`

**Purpose:** Client for SerpApi Google search.

---

## Public functions

#### `def sanitize_query_for_api(query) -> str`

**Purpose:** Remove internal boolean/site constraints before hitting raw APIs.

#### `def available_providers() -> list[HostedProvider]`

**Purpose:** Return instantiated providers that have keys in config.

---

## Private functions

#### `def _get_json(client, url, *, params, provider, headers=…) -> Any | None`

**Purpose:** Generic JSON GET helper with logging.

#### `def _post_json(client, url, *, json, provider, headers=…) -> Any | None`

**Purpose:** Generic JSON POST helper with logging.

---

## Related

- [search/_index](../_index/)
