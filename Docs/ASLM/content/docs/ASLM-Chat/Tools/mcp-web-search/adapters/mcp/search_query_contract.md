---
title: "search_query_contract"
draft: false
---

## Module `search_query_contract`

`Tools/mcp-web-search/adapters/mcp/search_query_contract.py` — ASLM Chat Python module.

---

## Public functions

#### `def coerce_search_effort(value) -> str`

**Purpose:** Normalize the public search effort argument.

**Steps:**

1. Return the computed result to the caller.

#### `def coerce_search_query(value) -> str`

**Purpose:** Convert the public query argument into one provider-ready search string.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def sanitize_legacy_query(query) -> str`

**Purpose:** Collapse whitespace and cap legacy free-text queries at 220 characters.

---

## Private functions

#### `def _try_parse_json(value) -> Any`

**Purpose:** Best-effort JSON parse for string tool arguments that look like objects.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

---

## Related

- [mcp/_index](../../../../_index/)
