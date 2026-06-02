---
title: "tools"
draft: false
---

## Module `tools`

`Tools/mcp-sandbox/supervisor/sandbox/tools.py` — ASLM Chat Python module.

---

## Public functions

#### `def register_tools(mcp) -> None`

**Purpose:** Register sandbox tools on a FastMCP instance.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

---

## Private functions

#### `async def _report_progress(ctx, progress, message) -> None`

**Purpose:** Send a best-effort progress notification when the client supports it.

**Steps:**

1. Await async I/O or subprocess work.
2. Handle errors and map them to a safe response.

---

## Related

- [sandbox/_index](../../../../_index/)
