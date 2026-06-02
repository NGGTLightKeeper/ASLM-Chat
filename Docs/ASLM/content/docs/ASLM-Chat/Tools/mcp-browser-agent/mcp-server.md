---
title: "mcp-server"
draft: false
---

## Module `mcp-server`

`Tools/mcp-browser-agent/mcp-server.py` — ASLM Chat Python module.

---

## Public functions

#### `def supports(engine, model_name) -> bool`

**Purpose:** Expose this tool server for engines that support tool-calling.

#### `async def call_tool(tool_id, arguments, context) -> Any`

**Purpose:** Generic ASLM-compatible dispatcher for Browser Agent tools.

#### `def register_tools(server) -> None`

**Purpose:** Attach Browser Agent tools to the provided MCP server instance.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.
5. Parse or serialize JSON payloads.

---

## Private functions

#### `def _flatten_content(content) -> str`

**Purpose:** Convert MCP-style content payloads into plain text for local tool execution.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `async def _run_with_keepalive(coro, session, interval, message)`

**Purpose:** Run a coroutine while optionally sending keepalive logs to an MCP session.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def _browser_keepalive_settings(name, arguments) -> tuple[float, str]`

**Purpose:** Pick keepalive interval and status message for a given browser tool name.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `async def _execute_browser_tool_local(name, arguments, context) -> Any`

**Purpose:** Execute one browser action in-process and return plain text or structured output.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def _execute_browser_tool(name, arguments, context) -> Any`

**Purpose:** Execute one browser action through the worker subprocess or inline when configured.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

#### `def _make_tool_handler(tool_id)`

**Purpose:** Build an ASLM-compatible per-tool wrapper that delegates to _execute_browser_tool.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

---

## Related

- [mcp-browser-agent/_index](../../_index/)
