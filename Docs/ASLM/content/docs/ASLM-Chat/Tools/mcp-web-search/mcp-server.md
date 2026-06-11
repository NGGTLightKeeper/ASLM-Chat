---
title: "mcp-server"
draft: false
---

## Module `mcp-server`

`Tools/mcp-web-search/mcp-server.py` — ASLM Chat Python module.

---

## Public functions

#### `def supports(engine, model_name) -> bool`

**Purpose:** Return whether this server supports the given engine or model.

#### `async def call_tool(tool_id, arguments, context) -> dict[str, Any]`

**Purpose:** Dispatch an ASLM tool call to the SERP search implementation.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

---

## Related

- [mcp-web-search/_index](../../_index/)
