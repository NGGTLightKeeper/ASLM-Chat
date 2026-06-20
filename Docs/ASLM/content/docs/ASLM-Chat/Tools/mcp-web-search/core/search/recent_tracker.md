---
title: "recent_tracker"
draft: false
---

## Module `recent_tracker`

`Tools/mcp-web-search/core/search/recent_tracker.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/search`.

---

## Classes

### `class RecentSearchTracker`

**Purpose:** Implements `RecentSearchTracker`.

#### `def RecentSearchTracker.__init__(self) -> None`

**Purpose:** Implements `__init__`.

#### `def RecentSearchTracker.query_key(query, region, safesearch, timelimit, effort, shopping, academic) -> str`

**Purpose:** Implements `query_key`.

#### `def RecentSearchTracker._prune(self, now, horizon) -> None`

**Purpose:** Implements `_prune`.

#### `def RecentSearchTracker.repeat_age(self, query_key, window) -> ...`

**Purpose:** Implements `repeat_age`.

#### `def RecentSearchTracker.recently_seen(self, urls, window) -> set[...]`

**Purpose:** Implements `recently_seen`.

#### `def RecentSearchTracker.record(self, query_key, urls, horizon) -> None`

**Purpose:** Implements `record`.

---

## Public functions

#### `def get_recent_tracker() -> RecentSearchTracker`

**Purpose:** Implements `get_recent_tracker`.

---

## Related

- [search/_index](../../_index/)
