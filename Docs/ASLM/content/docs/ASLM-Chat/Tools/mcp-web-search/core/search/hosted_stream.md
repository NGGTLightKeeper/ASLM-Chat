---
title: "hosted_stream"
draft: false
---

## Module `hosted_stream`

`Tools/mcp-web-search/core/search/hosted_stream.py` — ASLM Chat Python module.

---

## Public functions

#### `async def hosted_search_stream(query, *, region=…, max_results=…, deadline_seconds=…, providers=…) -> AsyncIterator[dict[str, Any]]`

**Purpose:** Yield search events from configured hosted APIs concurrently.

**Steps:**

1. Await async I/O or subprocess work.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _host_of(url) -> str`

**Purpose:** Return the lowercased host of a URL, or an empty string.

**Steps:**

1. Return the computed result to the caller.

#### `def _is_nav_junk(result) -> bool`

**Purpose:** Reject obvious navigation/SEO junk from content-bearing providers.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [search/_index](../_index/)
