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

**Purpose:** Fetch thread JSON API and format post title, body, and nested comments as markdown.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

---

## Related

- [custom_domains/_index](../../../_index/)
