---
title: "search_io_logger"
draft: false
---

## Module `search_io_logger`

`Tools/mcp-web-search/adapters/mcp/search_io_logger.py` — ASLM Chat Python module.

---

## Public functions

#### `def write_search_io_event(event) -> None`

**Purpose:** Append one full search/read-page IO event to a readable JSON array.

**Steps:**

1. Handle errors and map them to a safe response.
2. Parse or serialize JSON payloads.

---

## Private functions

#### `def _jsonable(value) -> Any`

**Purpose:** Coerce a value to something JSON-serializable for the IO log.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _without_duplicate_preview(value) -> Any`

**Purpose:** Drop redundant preview fields when they duplicate the snippet text.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [mcp/_index](../../../../_index/)
