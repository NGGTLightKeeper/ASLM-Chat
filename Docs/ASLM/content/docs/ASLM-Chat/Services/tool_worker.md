---
title: "tool_worker"
draft: false
---

## Module `tool_worker`

`Services/tool_worker.py` — ASLM Chat Python module.

---

## Overview

Loads a tool `mcp-server.py` in an isolated process and serves describe/supports/call over newline-delimited JSON.


---

## Classes

### `class AsyncCallableRunner`

**Purpose:** Type `AsyncCallableRunner` defined in `tool_worker.py`.

---

## Public functions

#### `def AsyncCallableRunner.__init__() -> None`

**Purpose:** Implements `AsyncCallableRunner.__init__` in `tool_worker.py`.

#### `def AsyncCallableRunner.ensure_started() -> None`

**Purpose:** Start the background loop thread when it is not already running.

#### `def AsyncCallableRunner.run(coro) -> Any`

**Purpose:** Execute one coroutine on the background loop and block for the result.

**Steps:**

1. Return the computed result to the caller.

#### `def AsyncCallableRunner.close() -> None`

**Purpose:** Stop the background loop and join its thread.

#### `def describe(server_file) -> dict[str, Any]`

**Purpose:** Return public metadata and tool list for one tool server file.

**Steps:**

1. Return the computed result to the caller.

#### `def supports(server_file, payload) -> bool`

**Purpose:** Return whether the server supports the requested engine and model pair.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def call(server_file, payload) -> Any`

**Purpose:** Execute one tool call against a server module.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def serve(server_file) -> int`

**Purpose:** Run a persistent newline-delimited JSON worker on stdin until EOF.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def main() -> int`

**Purpose:** CLI entry point for one-shot and persistent worker modes.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

---

## Private functions

#### `def AsyncCallableRunner._thread_main() -> None`

**Purpose:** Own the asyncio loop inside a dedicated daemon thread.

#### `def _slugify(value) -> str`

**Purpose:** Normalize public identifiers into stable lower-case slugs.

#### `def _load_module(server_file) -> ModuleType`

**Purpose:** Load one tool server module from disk and register its folder on sys.path.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def _server_metadata(module, folder_name) -> dict[str, Any]`

**Purpose:** Read MCP_SERVER (or SERVER) metadata from a loaded module.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def _normalize_schema(schema) -> dict[str, Any]`

**Purpose:** Normalize one JSON-schema-like tool parameters object.

**Steps:**

1. Return the computed result to the caller.

#### `def _server_tools(module, server_id) -> list[dict[str, Any]]`

**Purpose:** Build normalized tool definitions from a module TOOLS export.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def _tool_handlers(module) -> dict[str, Any]`

**Purpose:** Collect explicit per-tool handler callables from the module.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _server_callable(module)`

**Purpose:** Return the generic tool dispatcher callable when the module exports one.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _execute_callable(callable_fn, *args) -> Any`

**Purpose:** Invoke sync or async callables, routing coroutines through the shared loop.

#### `def _dispatch_server_callable(callable_fn, tool_id, arguments, context) -> Any`

**Purpose:** Call a generic dispatcher using a tolerant signature-matching strategy.

**Steps:**

1. Return the computed result to the caller.

#### `def _to_jsonable(value) -> Any`

**Purpose:** Convert arbitrary return values into JSON-serializable data.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _print_response(ok, payload, *, output=…) -> int`

**Purpose:** Print one JSON worker envelope to stdout.

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

#### `def _worker_heartbeat(output) -> None`

**Purpose:** Emit one protocol-safe heartbeat line for the parent process.

#### `def _execute_request(operation, server_file, payload) -> tuple[bool, Any]`

**Purpose:** Execute one worker request without printing the envelope.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

---

## Related

- [Services/_index](../_index/)
