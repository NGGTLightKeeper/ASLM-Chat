---
title: "router"
draft: false
---

## Module `router`

`Tools/mcp-web-search/custom_domains/router.py` — ASLM Chat Python module.

---

## Classes

### `class CustomRoute`

**Purpose:** Type `CustomRoute` defined in `router.py`.

---

## Public functions

#### `async def CustomRoute.fetch_preview(url, timeout) -> str | None`

**Purpose:** Run route fetch with asyncio timeout; return None on failure or timeout.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def get_custom_route(url) -> CustomRoute | None`

**Purpose:** Return the first custom route that matches the URL, or None.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _host(url) -> str`

**Purpose:** Normalize URL host (strip www./m. prefixes).

#### `async def _amazon_fetch(url, timeout) -> str | None`

**Purpose:** Amazon snapshot → markdown; drop blocked or empty pages.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

#### `async def _reddit_fetch(url, timeout) -> str | None`

**Purpose:** Reddit JSON thread → markdown; drop error strings.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

#### `async def _x_fetch(url, timeout) -> str | None`

**Purpose:** X/Twitter post → markdown; drop error strings.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

#### `async def _github_fetch(url, timeout) -> str | None`

**Purpose:** GitHub API page → markdown; drop error-prefixed responses.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

#### `async def _heavy_noop(url, timeout) -> str | None`

**Purpose:** Placeholder for heavy routes handled outside the router preview path.

---

## Related

- [custom_domains/_index](../../../_index/)
