---
title: "reddit"
draft: false
---

## Module `reddit`

`Tools/mcp-web-search/custom_domains/reddit.py` — ASLM Chat Python module.

---

## Public functions

#### `def is_reddit(url) -> bool`

**Purpose:** True when URL looks like a Reddit thread comments page.

#### `async def fetch_reddit_json(url) -> str`

**Purpose:** Fetch thread: curl_cffi JSON first, then warm-browser render as fallback.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

---

## Private functions

#### `async def _fetch_reddit_browser_page(thread_url, timeout) -> str | None`

**Purpose:** Fetch the rendered thread page via the warm cloakbrowser; return cleaned inner_text markdown.

## Related

- [custom_domains/_index](../../../_index/)
