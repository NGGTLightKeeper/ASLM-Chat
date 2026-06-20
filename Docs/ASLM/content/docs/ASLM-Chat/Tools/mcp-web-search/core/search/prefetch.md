---
title: "prefetch"
draft: false
---

## Module `prefetch`

`Tools/mcp-web-search/core/search/prefetch.py` — ASLM Chat Python module.

---

## Classes

### `class PrefetchManager`

**Purpose:** Manages tracked background warm-up tasks for result URLs.

---

## Public functions

#### `def PrefetchManager.__init__(*, max_concurrency=…, per_url_timeout=…, task_timeout=…) -> None`

**Purpose:** Implements `PrefetchManager.__init__` in `prefetch.py`.

#### `def PrefetchManager.schedule(urls) -> asyncio.Task | None`

**Purpose:** Schedule a tracked warm-up task for the given URLs. Returns the task (or None).

#### `async def PrefetchManager.shutdown() -> None`

**Purpose:** Cancel and await all outstanding warm-up tasks (call at server shutdown).

#### `def get_prefetch_manager() -> PrefetchManager`

**Purpose:** Return the lazily-initialised global PrefetchManager, configured from search_config.

#### `async def shutdown_prefetch() -> None`

**Purpose:** Cancel all outstanding prefetch tasks (exposed for the MCP server's shutdown hook).

---

## Private functions

#### `async def PrefetchManager._warm_one(url) -> bool`

**Purpose:** Warm one URL's raw HTML into the page cache under read_page's cache key.

#### `async def PrefetchManager._warm_batch(urls) -> None`

**Purpose:** Warm a batch of URLs under one hard-timeout-bounded task.

---

## Related

- [search/_index](../_index/)
