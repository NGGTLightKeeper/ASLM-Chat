---
title: "query_normalizer"
draft: false
---

## Module `query_normalizer`

`Tools/mcp-web-search/core/cache/query_normalizer.py` — ASLM Chat Python module.

---

## Public functions

#### `def normalize_query_key(query) -> str`

**Purpose:** Canonical cache key: lowercase, stopwords removed, terms sorted (order discarded).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def normalize_exact_query_key(query) -> str`

**Purpose:** Order-preserving canonical query string for strict cache keys.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [cache/_index](../../../../_index/)
