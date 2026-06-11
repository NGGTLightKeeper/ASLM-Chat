---
title: "profiles"
draft: false
---

## Module `profiles`

`Tools/mcp-web-search/core/fetch/profiles.py` — ASLM Chat Python module.

---

## Classes

### `BrowserProfile`

**Purpose:** A complete browser identity used to build convincing request metadata.

---

## Public functions

#### `def pick() -> BrowserProfile`

**Purpose:** Pick a random browser profile from the pool.

**Steps:**

1. Return the computed result to the caller.

#### `def build_nav_headers(profile, referer, sec_fetch_site, extra) -> dict[str, str]`

**Purpose:** Build the full header set for a navigation request using the given profile.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [fetch/_index](../_index/)
