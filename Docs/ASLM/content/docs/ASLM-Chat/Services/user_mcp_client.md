---
title: "user_mcp_client"
draft: false
---

## Module `user_mcp_client`

`Services/user_mcp_client.py` — ASLM Chat Python module.

---

## Public functions

#### `def shutdown_all() -> None`

**Purpose:** Release per-server locks (reserved for future persistent sessions).

#### `def fetch_tool_definitions(entry) -> tuple[list[dict[str, Any]], str | None]`

**Purpose:** Connect once, list tools, and disconnect (serialized per server id).

#### `def call_user_mcp_tool(entry, mcp_tool_name, arguments) -> str`

**Purpose:** Run one MCP tool call with a new connection per invocation.

---

## Private functions

#### `def _normalize_parameters_schema(schema) -> dict[str, Any]`

**Purpose:** Normalize MCP tool input schemas into JSON Schema objects.

**Steps:**

1. Return the computed result to the caller.

#### `def _tool_definitions_from_mcp_tools(server_id, mcp_tools) -> tuple[list[dict[str, Any]], str | None]`

**Purpose:** Convert MCP list_tools results into ASLM tool definition payloads.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _format_call_tool_result(result) -> str`

**Purpose:** Format one MCP call_tool result as plain text for the chat layer.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.
3. Parse or serialize JSON payloads.

#### `async def _connect_session(entry)`

**Purpose:** Implements `_connect_session` in `user_mcp_client.py`.

**Steps:**

1. Await async I/O or subprocess work.

#### `async def _list_tools_async(entry) -> tuple[list[dict[str, Any]], str | None]`

**Purpose:** List tools from one user MCP server over a fresh connection.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def _call_tool_async(entry, mcp_tool_name, arguments) -> str`

**Purpose:** Invoke one MCP tool over a fresh connection.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

---

## Related

- [Services/_index](../_index/)
