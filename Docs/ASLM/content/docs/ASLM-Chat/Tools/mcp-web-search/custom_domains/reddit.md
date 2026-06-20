---
title: "reddit"
draft: false
---

## Module `reddit`

`Tools/mcp-web-search/custom_domains/reddit.py` — ASLM Chat Python module.

---

## Public functions

#### `def reddit_json_url(url) -> str`

**Purpose:** Build the thread .json endpoint (limit/depth query for comments).

**Steps:**

1. Return the computed result to the caller.

#### `def reddit_thread_url(url) -> str`

**Purpose:** Thread page URL without the .json suffix (used as Referer).

**Steps:**

1. Return the computed result to the caller.

#### `def parse_reddit_json_payload(raw) -> list[Any] | None`

**Purpose:** Parse Reddit listing JSON from raw text or minimal HTML wrapper.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def reddit_data_to_markdown(data, url) -> str`

**Purpose:** Format Reddit thread JSON as markdown (post + nested comments).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def is_reddit(url) -> bool`

**Purpose:** True when URL looks like a Reddit thread comments page.

#### `async def fetch_reddit_json(url, timeout=…) -> str`

**Purpose:** Fetch thread via .json suffix: curl_cffi first, then Camoufox on the same URL.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

---

## Private functions

#### `def _fetch_reddit_json_curl(json_url, thread_url, timeout) -> list[Any] | None`

**Purpose:** Fetch thread JSON via curl_cffi TLS impersonation.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `async def _fetch_reddit_json_camoufox(thread_url, timeout) -> list[Any] | None`

**Purpose:** Open thread HTML in Camoufox, then fetch .json in-page when curl_cffi is blocked.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

---

## Related

- [custom_domains/_index](../../../_index/)
