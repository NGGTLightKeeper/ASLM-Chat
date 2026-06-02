---
title: "hosted_clients"
draft: false
---

## Module `hosted_clients`

`Tools/mcp-web-search/core/fetch/hosted_clients.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\fetch`. See **Related** for package index and callers.

---

## Classes

### `class TavilyClient`

**Purpose:** Type `TavilyClient` defined in `hosted_clients.py`.

### `class BraveClient`

**Purpose:** Type `BraveClient` defined in `hosted_clients.py`.

### `class BingClient`

**Purpose:** Type `BingClient` defined in `hosted_clients.py`.

### `class SerpApiClient`

**Purpose:** Type `SerpApiClient` defined in `hosted_clients.py`.

---

## Public functions

#### `def available_hosted_engines() -> list[str]`

**Purpose:** Return hosted engine names that have an API key configured.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def TavilyClient.search_with_content(query, max_results, *, timelimit=…, search_depth=…) -> tuple[list[SearchResult], dict[str, str]]`

**Purpose:** POST search; returns results plus url→full_text map for SourceCache.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def TavilyClient.search(query, max_results, *, timelimit=…, search_depth=…) -> list[SearchResult]`

**Purpose:** Search without returning the raw_content side map.

**Steps:**

1. Return the computed result to the caller.

#### `def BraveClient.search_with_content(query, max_results, *, timelimit=…) -> tuple[list[SearchResult], dict[str, str]]`

**Purpose:** GET web search results and retain the full provider payload.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def BraveClient.search(query, max_results, *, timelimit=…) -> list[SearchResult]`

**Purpose:** Implements `BraveClient.search` in `hosted_clients.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def BingClient.search_with_content(query, max_results, *, timelimit=…) -> tuple[list[SearchResult], dict[str, str]]`

**Purpose:** GET web search results and retain the full provider payload.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def BingClient.search(query, max_results, *, timelimit=…) -> list[SearchResult]`

**Purpose:** Implements `BingClient.search` in `hosted_clients.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def SerpApiClient.search_with_content(query, max_results, *, timelimit=…) -> tuple[list[SearchResult], dict[str, str]]`

**Purpose:** GET Google organic results via SerpAPI and retain the full provider payload.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def SerpApiClient.search(query, max_results, *, timelimit=…) -> list[SearchResult]`

**Purpose:** Implements `SerpApiClient.search` in `hosted_clients.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def search_with_hosted(engine, query, max_results, *, timelimit=…, query_type=…, bypass_cache=…) -> list[SearchResult]`

**Purpose:** Sync dispatch with HostedSearchCache get → API → set.

**Steps:**

1. Return the computed result to the caller.

#### `def search_with_hosted_content(engine, query, max_results, *, timelimit=…, query_type=…, bypass_cache=…) -> tuple[list[SearchResult], dict[str, str]]`

**Purpose:** Search a hosted provider and return both SERP results and provider text.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `async def async_hosted_search(engine, query, max_results, *, timelimit=…, query_type=…) -> list[SearchResult]`

**Purpose:** Async hosted search in thread; hosted provider payloads pre-populate SourceCache.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

---

## Private functions

#### `def _get_pool() -> ThreadPoolExecutor`

**Purpose:** Thread pool for sync hosted API calls.

**Steps:**

1. Return the computed result to the caller.

#### `def _get_page_cache()`

**Purpose:** Shared SourceCache for Tavily raw_content pre-population.

**Steps:**

1. Return the computed result to the caller.

#### `def _wrap_as_html(text) -> str`

**Purpose:** Wrap plain text in minimal HTML for SourceCache / preview pipeline.

#### `def _append_hosted_text(parts, label, value, seen) -> None`

**Purpose:** Collect all useful text from a hosted provider result item.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _hosted_item_content(item, *, first_fields=…) -> str`

**Purpose:** Return the complete text payload a hosted provider exposed for one result.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _cache_hosted_content(engine, results, content_map) -> None`

**Purpose:** Pre-populate SourceCache so hosted result text goes through preview parsing.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def _result_hash(results) -> int`

**Purpose:** Stable hash of top-5 URLs for router telemetry.

#### `def _sanitize_query_for_api(query) -> str`

**Purpose:** Strip characters that break hosted API parsers ([ ] * \ unbalanced quotes).

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [fetch/_index](../../../../_index/)
