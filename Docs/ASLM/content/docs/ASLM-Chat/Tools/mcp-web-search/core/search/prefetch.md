---
title: "prefetch"
draft: false
---

## Module `prefetch`

`Tools/mcp-web-search/core/search/prefetch.py` — ASLM Chat Python module.

---

## Classes

#### `class PrefetchManager`

**Purpose:** Manages background prefetching of search result URLs. Process discipline this is NOT fire-and-forget. Every warm-up is one tracked asyncio.Task held in a registry, bounded by a hard timeout and a concurrency semaphore, self-removing on completion, and cancellable via shutdown(). The legacy prefetch was fire-and-forget; this is the disciplined replacement.

**Methods:**
- `schedule(self, urls: list[str]) -> asyncio.Task | None:` Schedule a tracked warm-up task for the given URLs. Returns the task (or None).

---

## Related

- [search/_index](../_index/)
