---
title: "browser_worker"
draft: false
---

## Module `browser_worker`

`Tools/mcp-browser-agent/browser_worker.py` — ASLM Chat Python module.

---

## Public functions

#### `def main() -> None`

**Purpose:** Read JSON requests from stdin until a shutdown command ends the worker loop.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.
3. Parse or serialize JSON payloads.

---

## Private functions

#### `def _load_mcp_server_module()`

**Purpose:** Load the MCP server module from the sibling mcp-server.py file.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def _debug_context(request) -> dict[str, Any]`

**Purpose:** Build a normalized debug context dict from an incoming worker request.

**Steps:**

1. Return the computed result to the caller.

#### `def _debug_event(request, event, **fields) -> None`

**Purpose:** Emit a debug event (intentionally disabled; kept for call-site compatibility).

#### `async def _close_browser_state() -> None`

**Purpose:** Close the shared browser state and stop the dedicated browser event loop.

**Steps:**

1. Await async I/O or subprocess work.
2. Handle errors and map them to a safe response.

#### `async def _handle_request(request) -> dict[str, Any]`

**Purpose:** Dispatch one JSON-line worker request to a browser tool or shutdown command.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

#### `def _write_response(response) -> None`

**Purpose:** Write one JSON response line to stdout for the parent process.

---

## Related

- [mcp-browser-agent/_index](../../_index/)
