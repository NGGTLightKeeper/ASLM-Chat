---
title: "google"
draft: false
---

## Module `google`

`Tools/mcp-web-search/core/engines/google.py` — ASLM Chat Python module.

---

## Classes

### `GoogleParser`

**Purpose:** Google SERP parser with structural fallbacks and degradation reporting.

#### `def build_request(query, region, safesearch, timelimit, page) -> EngineRequest`

**Purpose:** Build the HTTP request for a Google search query using a random browser profile.

**Steps:**

1. Return the computed result to the caller.

#### `def parse(self, document) -> EngineParseResult`

**Purpose:** Parse a raw Google SERP HTML document into an EngineParseResult.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _unwrap_url(value) -> str`

**Purpose:** Unwrap a Google redirect URL to the actual destination URL.

**Steps:**

1. Return the computed result to the caller.

#### `def _is_internal(value) -> bool`

**Purpose:** Return True when the URL points to a Google-owned domain.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [engines/_index](../_index/)
