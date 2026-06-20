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

**Purpose:** Fetch a thread through a tiered fallback that degrades on antibot blocks: 1. curl_cffi .json (www) — fast, no browser; Reddit increasingly 403s this 2. warm-browser .json (www) — JSON behind the browser identity (clean structured md) 3. warm-browser .json (old) — same on old.reddit.com (lighter, less guarded host) 4. warm-browser page (old) — last resort: render old.reddit and strip nav cruft

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

---

## Related

- [custom_domains/_index](../../../_index/)
