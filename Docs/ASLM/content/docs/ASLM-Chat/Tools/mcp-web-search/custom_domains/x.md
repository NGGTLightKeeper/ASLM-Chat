---
title: "x"
draft: false
---

## Module `x`

`Tools/mcp-web-search/custom_domains/x.py` — ASLM Chat Python module.

---

## Public functions

#### `def x_status_id(url) -> str | None`

**Purpose:** Extract numeric status id from an X/Twitter post URL path.

**Steps:**

1. Return the computed result to the caller.

#### `def is_x_post(url) -> bool`

**Purpose:** True when URL is an x.com/twitter.com status permalink.

#### `def parse_x_syndication_payload(data, url) -> str`

**Purpose:** Format syndication API JSON into readable markdown.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def parse_x_oembed_payload(data, url) -> str`

**Purpose:** Format oEmbed HTML payload into readable markdown.

**Steps:**

1. Return the computed result to the caller.

#### `async def fetch_x_post(url, timeout) -> str`

**Purpose:** Fetch post via syndication API, then oEmbed fallback; return markdown or error string.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

---

## Private functions

#### `def _host(url) -> str`

**Purpose:** Normalize URL host (strip www./m. prefixes).

#### `def _x_fetch_json(endpoint, timeout) -> dict | None`

**Purpose:** GET JSON from syndication or oEmbed endpoint via curl_cffi.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

---

## Related

- [custom_domains/_index](../../../_index/)
