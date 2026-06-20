---
title: "hosted_cache"
draft: false
---

## Module `hosted_cache`

`Tools/mcp-web-search/core/cache/hosted_cache.py` — ASLM Chat Python module.

---

## Classes

### `class HostedSearchCache`

**Purpose:** Type `HostedSearchCache` defined in `hosted_cache.py`.

---

## Public functions

#### `def query_ttl(query_type) -> int`

**Purpose:** Return cache TTL in seconds for the given query classification.

#### `def HostedSearchCache.__init__(db_path) -> None`

**Purpose:** Implements `HostedSearchCache.__init__` in `hosted_cache.py`.

#### `def HostedSearchCache.make_key(query, *, region, safesearch, timelimit, effort, shopping, academic) -> str`

**Purpose:** Implements `HostedSearchCache.make_key` in `hosted_cache.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def HostedSearchCache.get(query, *, region, safesearch, timelimit, effort, shopping, academic) -> Optional[dict[str, Any]]`

**Purpose:** Return cached results or None if missing or expired.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def HostedSearchCache.set(query, payload, *, region, safesearch, timelimit, effort, shopping, academic, is_empty) -> None`

**Purpose:** Store results; empty list uses NEGATIVE_TTL.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.
3. Parse or serialize JSON payloads.

#### `def HostedSearchCache.evict_expired() -> int`

**Purpose:** Delete expired entries; returns number of deleted rows.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def HostedSearchCache.stats(provider) -> dict`

**Purpose:** Return basic cache statistics, optionally filtered by provider.

**Steps:**

1. Return the computed result to the caller.

#### `def get_hosted_cache() -> HostedSearchCache`

**Purpose:** Return the lazily initialised global HostedSearchCache.

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `def _result_to_dict(r) -> dict`

**Purpose:** Serialize a SearchResult for SQLite JSON storage.

**Steps:**

1. Return the computed result to the caller.

#### `def _dict_to_result(d) -> SearchResult`

**Purpose:** Deserialize a dict from hosted_cache back into SearchResult.

**Steps:**

1. Return the computed result to the caller.

#### `def HostedSearchCache._get_conn() -> sqlite3.Connection`

**Purpose:** Return a per-thread persistent SQLite connection.

**Steps:**

1. Return the computed result to the caller.

#### `def HostedSearchCache._init_db() -> None`

**Purpose:** Create hosted_cache table and indexes if needed.

---

## Related

- [cache/_index](../../../../_index/)
