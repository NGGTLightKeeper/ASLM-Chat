---
title: "ddgs_client"
draft: false
---

## Module `ddgs_client`

`Tools/mcp-web-search/core/fetch/ddgs_client.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\fetch`. See **Related** for package index and callers.

---

## Classes

### `class DDGSClient`

**Purpose:** Type `DDGSClient` defined in `ddgs_client.py`.

---

## Public functions

#### `def normalize_snippet(text) -> str`

**Purpose:** Universal snippet cleanup (no language-specific tokenization).

**Steps:**

1. Return the computed result to the caller.

#### `def DDGSClient.__init__(proxies, cache_db, cache_ttl, proxy_cooldown, request_delay, timeout, max_retries) -> None`

**Purpose:** Configure proxies, cache, delays, and retry policy.

#### `def DDGSClient.search_sync(query, max_results, backend, region, timelimit, cache_ttl) -> list[dict]`

**Purpose:** One synchronous DDGS search with retries, cache, and negative cache on empty.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def DDGSClient.search_to_results(query, max_results, backend, region, timelimit, cache_ttl) -> list[SearchResult]`

**Purpose:** search_sync mapped to SearchResult models with normalized snippets.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def DDGSClient.search_with_fallback(query, max_results, query_type, query_types, lang, timelimit, hedge_count, partial_buffer_path) -> list[SearchResult]`

**Purpose:** Router-driven hedged search; site: and non-en lang use static backend lists.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def get_ddgs_client(proxies, cache_db) -> DDGSClient`

**Purpose:** Lazily initialized global DDGS client singleton.

**Steps:**

1. Return the computed result to the caller.

#### `async def async_ddgs_search(query, max_results, query_type, query_types, lang, timelimit, use_subprocess, worker_timeout, hedge_count, engine_timeout, max_retries) -> list[SearchResult]`

**Purpose:** Async DDGS search; optional isolated subprocess for hard-kill on timeout.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.
5. Parse or serialize JSON payloads.
6. Spawn or communicate with a child process.

---

## Private functions

#### `def _get_pool() -> ThreadPoolExecutor`

**Purpose:** Dedicated thread pool for DDGS sync search (rate-limited sleeps).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _effective_ttl(query_types, timelimit) -> int`

**Purpose:** Shortest TTL across matched query types (e.g. finance + journalistic → 300s).

#### `def _union_preset_engines(query_types) -> list[str]`

**Purpose:** Union of BACKEND_PRESETS engines for all matched types (skips "auto").

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _serialise_results(results) -> list[dict]`

**Purpose:** Serialize SearchResult list for partial-timeout buffer file.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _write_partial_results(path, results) -> None`

**Purpose:** Merge and persist partial hedged-search results for worker timeout recovery.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.
3. Parse or serialize JSON payloads.

#### `def _read_partial_results(path) -> list[SearchResult]`

**Purpose:** Load partial results written before a subprocess worker timed out.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _timelimit_cache_ttl(timelimit, base_ttl) -> int`

**Purpose:** Cap cache TTL when a timelimit filter is active (fresher results expected).

**Steps:**

1. Return the computed result to the caller.

#### `def _extract_snippet_date(snippet) -> str`

**Purpose:** Parse leading date prefix from a DDGS snippet string.

#### `def DDGSClient._get_proxy() -> Optional[str]`

**Purpose:** Pick a random proxy not in cooldown.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def DDGSClient._block_proxy(proxy) -> None`

**Purpose:** Mark proxy as rate-limited until cooldown expires.

#### `def DDGSClient._init_cache() -> None`

**Purpose:** Create SQLite cache table if missing.

#### `def DDGSClient._cache_key(query, **kwargs) -> str`

**Purpose:** SHA-256 key from normalized query plus search parameters.

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

#### `def DDGSClient._cache_get(key) -> Optional[list]`

**Purpose:** Return cached raw DDGS rows if still within TTL.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def DDGSClient._cache_set(key, data, ttl) -> None`

**Purpose:** Store raw DDGS rows with optional per-entry TTL.

**Steps:**

1. Handle errors and map them to a safe response.
2. Parse or serialize JSON payloads.

#### `def DDGSClient._sanitize_query(query) -> str`

**Purpose:** Implements `DDGSClient._sanitize_query` in `ddgs_client.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def DDGSClient._degraded_query_variants(query) -> list[str]`

**Purpose:** Implements `DDGSClient._degraded_query_variants` in `ddgs_client.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def _query_preview(query, limit) -> str`

**Purpose:** Truncate query for log messages.

#### `def _deserialize_results(payload) -> list[SearchResult]`

**Purpose:** Rebuild SearchResult list from worker subprocess JSON payload.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [fetch/_index](../../../../_index/)
