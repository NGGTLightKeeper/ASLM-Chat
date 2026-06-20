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

#### `def HostedSearchCache.__init__(db_path, \*, default_ttl=…, negative_ttl=…) -> None`

**Purpose:** Implements `HostedSearchCache.__init__` in `hosted_cache.py`.

#### `def HostedSearchCache.make_key(query, *, region, safesearch, timelimit, effort, shopping, academic) -> str`

**Purpose:** Implements `HostedSearchCache.make_key` in `hosted_cache.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def HostedSearchCache.get(query, *, region, safesearch, timelimit, effort, shopping, academic) -> Optional[dict[str, Any]]`

**Purpose:** Return a cached payload, or None when missing/expired.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def HostedSearchCache.set(query, payload, *, region, safesearch, timelimit, effort, shopping, academic, is_empty) -> None`

**Purpose:** Store a payload. An empty result set gets the short negative TTL.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.
3. Parse or serialize JSON payloads.

#### `def HostedSearchCache.evict_expired() -> int`

**Purpose:** Delete expired entries; returns number of deleted rows.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def get_hosted_cache() -> HostedSearchCache`

**Purpose:** Return the lazily initialised global HostedSearchCache.

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `def HostedSearchCache._get_conn() -> sqlite3.Connection`

**Purpose:** Return a per-thread persistent SQLite connection.

**Steps:**

1. Return the computed result to the caller.

#### `def HostedSearchCache._init_db() -> None`

**Purpose:** Create hosted_cache table and indexes if needed.

---

## Related

- [cache/_index](../../../../_index/)
