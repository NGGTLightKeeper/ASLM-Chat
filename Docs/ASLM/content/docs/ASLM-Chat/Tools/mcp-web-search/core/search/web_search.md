---
title: "web_search"
draft: false
---

## Module `web_search`

`Tools/mcp-web-search/core/search/web_search.py` — ASLM Chat Python module.

---

## Public classes

### `class EffortProfile`

**Purpose:** Configuration for a specific search effort level.

### `class WebSearchService`

**Purpose:** Main service for running web searches and coordinating fetch, deduplication, triage, and parsing.

**Methods:**

- `async def search(query, effort, region, safesearch, timelimit) -> dict[str, Any]`
- `async def _parse_one(source, profile) -> None`

---

## Public functions

#### `def select_engines(effort, tracker) -> list[type]`

**Purpose:** Select active engines based on effort profile.

#### `async def run_web_search(query, effort, region, safesearch, timelimit) -> dict[str, Any]`

**Purpose:** Convenience entry point mirroring run_serp_search to execute a full web search.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

---

## Private classes

### `class _Source`

**Purpose:** Internal representation of a search source being tracked during the stream.

---

## Related

- [search/_index](../../_index/)
