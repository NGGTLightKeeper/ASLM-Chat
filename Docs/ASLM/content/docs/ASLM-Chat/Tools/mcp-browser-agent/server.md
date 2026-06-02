---
title: "server"
draft: false
---

## Module `server`

`Tools/mcp-browser-agent/server.py` — ASLM Chat Python module.

---

## Public functions

#### `def main() -> None`

**Purpose:** Parse CLI arguments and launch the selected transport.

---

## Private functions

#### `def _load_register_tools()`

**Purpose:** Load register_tools from the root mcp-server.py file.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `async def _run_stdio() -> None`

**Purpose:** Run MCP over stdio.

**Steps:**

1. Await async I/O or subprocess work.

#### `async def _run_http(host, port) -> None`

**Purpose:** Run MCP over streamable HTTP.

**Steps:**

1. Await async I/O or subprocess work.

---

## Related

- [mcp-browser-agent/_index](../../_index/)
