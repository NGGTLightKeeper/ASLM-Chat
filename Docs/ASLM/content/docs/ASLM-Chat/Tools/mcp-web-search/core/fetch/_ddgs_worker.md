---
title: "_ddgs_worker"
draft: false
---

## Module `_ddgs_worker`

`Tools/mcp-web-search/core/fetch/_ddgs_worker.py` — ASLM Chat Python module.

---

## Public functions

#### `def main() -> None`

**Purpose:** stdin: JSON request; stdout: one JSON line with results or error.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.
3. Parse or serialize JSON payloads.

---

## Private functions

#### `def _fail(msg) -> None`

**Purpose:** Write one JSON error line to stdout.

---

## Related

- [fetch/_index](../../../../_index/)
