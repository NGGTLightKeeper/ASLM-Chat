---
title: "_camoufox_worker"
draft: false
---

## Module `_camoufox_worker`

`Tools/mcp-web-search/core/fetch/_camoufox_worker.py` — ASLM Chat Python module.

---

## Public functions

#### `def main() -> None`

**Purpose:** stdin: JSON line; stdout: one JSON line with html or error.

**Steps:**

1. Handle errors and map them to a safe response.
2. Parse or serialize JSON payloads.

---

## Private functions

#### `def _ok(html, url, title, inner_text) -> None`

**Purpose:** Write success JSON (html, url, title, inner_text) to stdout.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def _fail(msg) -> None`

**Purpose:** Write error JSON to stdout.

#### `def _extract_title(html) -> str`

**Purpose:** Parse <title> from HTML for the worker response.

**Steps:**

1. Return the computed result to the caller.

#### `def _pick_os() -> str`

**Purpose:** Weighted random OS for browser fingerprint rotation.

#### `def _build_profile(locale) -> dict`

**Purpose:** Build locale-specific Camoufox browser profile dict.

**Steps:**

1. Return the computed result to the caller.

#### `async def _apply_profile(page, profile) -> None`

**Purpose:** Apply navigator and viewport overrides on the Playwright page.

**Steps:**

1. Await async I/O or subprocess work.
2. Handle errors and map them to a safe response.

#### `async def _human_scroll(page) -> None`

**Purpose:** Scroll the page partially to mimic human reading behavior.

**Steps:**

1. Await async I/O or subprocess work.
2. Handle errors and map them to a safe response.

#### `async def _warmup(page, warmup_urls, count, timeout_sec) -> None`

**Purpose:** Visit warmup URLs before the target to build a natural session.

**Steps:**

1. Await async I/O or subprocess work.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `async def _fetch(payload) -> None`

**Purpose:** Load url in Camoufox and emit HTML JSON on stdout.

**Steps:**

1. Await async I/O or subprocess work.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

---

## Related

- [fetch/_index](../../../../_index/)
