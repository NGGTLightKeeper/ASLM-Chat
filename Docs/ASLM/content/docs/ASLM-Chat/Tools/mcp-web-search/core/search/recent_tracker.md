---
title: "recent_tracker"
draft: false
---

## Module `recent_tracker`

`Tools/mcp-web-search/core/search/recent_tracker.py` — ASLM Chat Python module.

---

## Classes

### `class RecentSearchTracker`

**Purpose:** In-memory recency tracker for queries and served source URLs.

---

## Public functions

#### `def RecentSearchTracker.__init__() -> None`

**Purpose:** Implements `RecentSearchTracker.__init__` in `recent_tracker.py`.

#### `def RecentSearchTracker.query_key(query, *, region=…, safesearch=…, timelimit=…, effort=…) -> str`

**Purpose:** Composite identity of a query: normalized text + result-affecting params.

#### `def RecentSearchTracker.repeat_age(query_key, window) -> float | None`

**Purpose:** Seconds since this exact query was last served, or None if outside the window.

#### `def RecentSearchTracker.recently_seen(urls, window) -> set[str]`

**Purpose:** Return the subset of urls served to the model within the suppression window.

#### `def RecentSearchTracker.record(query_key, urls, *, horizon=…) -> None`

**Purpose:** Record that this query and these source URLs were just served to the model.

#### `def get_recent_tracker() -> RecentSearchTracker`

**Purpose:** Return the lazily-initialised global tracker.

---

## Private functions

#### `def RecentSearchTracker._prune(now, horizon) -> None`

**Purpose:** Drop entries older than the larger of the two windows (cheap housekeeping).

---

## Related

- [search/_index](../_index/)
