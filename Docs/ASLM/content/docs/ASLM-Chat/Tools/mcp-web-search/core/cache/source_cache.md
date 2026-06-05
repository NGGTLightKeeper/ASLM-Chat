---
title: "source_cache"
draft: false
---

## Module `source_cache`

`Tools/mcp-web-search/core/cache/source_cache.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\cache`. See **Related** for package index and callers.

---

## Classes

### `class CachedPage`

**Purpose:** Type `CachedPage` defined in `source_cache.py`.

### `class SourceCache`

**Purpose:** Type `SourceCache` defined in `source_cache.py`.

---

## Public functions

#### `def canonicalize_url(url) -> str`

**Purpose:** Normalize URL for dedup: https, strip www, sort/filter query params.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def url_hash(url) -> str`

**Purpose:** SHA-256 of canonical URL.

#### `def content_hash(text) -> str`

**Purpose:** SHA-256 of page text content.

#### `def SourceCache.__init__(db_path, default_ttl) -> None`

**Purpose:** Implements `SourceCache.__init__` in `source_cache.py`.

#### `def SourceCache.search_local(query, limit, min_freshness_sec) -> list[CachedPage]`

**Purpose:** FTS5 + BM25 search over cached pages (status=ok, within freshness window).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def SourceCache.cache_page(url, title, clean_text, raw_html, domain, status) -> None`

**Purpose:** Insert or update a page (pages + FTS5 in one transaction).

**Steps:**

1. Handle errors and map them to a safe response.

#### `def SourceCache.get_cached(url) -> Optional[CachedPage]`

**Purpose:** Return a cached page by URL, or None.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def SourceCache.is_fresh(url, max_age_sec) -> bool`

**Purpose:** True when a cached ok page exists and is younger than max_age_sec.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def SourceCache.record_query_source(query, url, rank) -> None`

**Purpose:** Associate a query with a source URL for stats and future ranking.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def SourceCache.record_query_source_classes(query, url, *, class_mix_json=…, content_classes_json=…, snippet_score=…, parsed_score=…) -> None`

**Purpose:** Attach class/relevance metadata to a query-source observation.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def SourceCache.page_count() -> int`

**Purpose:** Total number of cached pages.

#### `def SourceCache.cache_stats() -> dict`

**Purpose:** Basic cache statistics (totals and distinct queries).

**Steps:**

1. Return the computed result to the caller.

#### `def SourceCache.evict_stale(max_age_sec) -> int`

**Purpose:** Delete stale pages and related query_sources; returns deleted count.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _is_sqlite_corruption(exc) -> bool`

**Purpose:** True when a sqlite3 error indicates a corrupt on-disk database.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def SourceCache._get_conn() -> sqlite3.Connection`

**Purpose:** Return a per-thread persistent SQLite connection.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def SourceCache._close_thread_conn() -> None`

**Purpose:** Close the current thread's SQLite connection.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def SourceCache._recover_corrupt_db(exc) -> bool`

**Purpose:** Quarantine corrupt DB files and recreate an empty cache.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def SourceCache._init_db() -> None`

**Purpose:** Apply schema DDL on first open (or after corruption recovery).

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

---

## Related

- [cache/_index](../../../../_index/)
