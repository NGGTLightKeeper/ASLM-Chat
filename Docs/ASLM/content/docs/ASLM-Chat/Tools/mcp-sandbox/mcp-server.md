---
title: "mcp-server"
draft: false
---

## Module `mcp-server`

`Tools/mcp-sandbox/mcp-server.py` — ASLM Chat Python module.

---

## Public functions

#### `def supports(engine, model_name) -> bool`

**Purpose:** Expose this tool server for engines that support tool-calling.

#### `def call_tool(tool_id, arguments, context) -> dict[str, Any]`

**Purpose:** Dispatch one sandbox v2 tool.

**Steps:**

1. Return the computed result to the caller.

#### `def register_tools(mcp) -> None`

**Purpose:** Register sandbox tools on a FastMCP instance.

---

## Related

- [mcp-sandbox/_index](../../_index/)
