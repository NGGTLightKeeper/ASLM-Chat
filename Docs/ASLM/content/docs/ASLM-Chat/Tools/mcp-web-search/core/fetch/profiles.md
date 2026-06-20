---
title: "profiles"
draft: false
---

## Module `profiles`

`Tools/mcp-web-search/core/fetch/profiles.py` — ASLM Chat Python module.

---

## Classes

### `class BrowserProfile`

**Purpose:** A complete browser identity used to build convincing request metadata.

#### Public Methods

- `def is_chromium() -> bool`
  - **Purpose:** Returns whether the browser profile is part of the Chromium family.

---

## Public functions

#### `def pick() -> BrowserProfile`

**Purpose:** Picks a random browser profile from the pool (legacy/benchmark baseline).

#### `def for_engine(key, *, generation) -> BrowserProfile`

**Purpose:** Deterministically maps an engine key to a fixed browser profile identity.

#### `def accept_language_for(language, country) -> str`

**Purpose:** Builds an Accept-Language header coherent with the query's inferred language.

#### `def build_nav_headers(profile, *, referer, sec_fetch_site, extra) -> dict[str, str]`

**Purpose:** Builds the full header set for a navigation request using the given profile.

---

## Related

- [_index](../_index/)
