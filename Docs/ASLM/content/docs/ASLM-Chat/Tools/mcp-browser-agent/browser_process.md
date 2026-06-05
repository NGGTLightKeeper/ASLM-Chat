---
title: "browser_process"
draft: false
---

## Module `browser_process`

`Tools/mcp-browser-agent/browser_process.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-browser-agent`. See **Related** for package index and callers.

---

## Classes

### `class BrowserProcessManager`

**Purpose:** Type `BrowserProcessManager` defined in `browser_process.py`.

---

## Public functions

#### `def BrowserProcessManager.__init__() -> None`

**Purpose:** Initialize empty worker process handles and idle-timer state.

**Steps:**

1. Spawn or communicate with a child process.

#### `async def BrowserProcessManager.call(tool_name, arguments, context, *, session=…, interval=…, message=…) -> Any`

**Purpose:** Dispatch a browser tool call to the worker with idle timer and restore logic.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

#### `async def BrowserProcessManager.shutdown(*, reason=…) -> None`

**Purpose:** Gracefully shut down the worker subprocess, killing it if needed.

**Steps:**

1. Await async I/O or subprocess work.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

---

## Private functions

#### `def _json_safe_context(context) -> dict[str, Any]`

**Purpose:** Strip non-serializable fields from the tool context before sending to the worker.

**Steps:**

1. Return the computed result to the caller.

#### `def BrowserProcessManager._cancel_idle_timer() -> None`

**Purpose:** Cancel the pending idle-shutdown timer if one is scheduled.

#### `def BrowserProcessManager._schedule_idle_timer() -> None`

**Purpose:** Schedule worker shutdown after the configured idle timeout.

#### `async def BrowserProcessManager._ensure_process() -> asyncio.subprocess.Process`

**Purpose:** Spawn the browser worker subprocess when it is not already running.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Spawn or communicate with a child process.

#### `async def BrowserProcessManager._read_response(process, request_id, *, context, session, interval, message) -> dict[str, Any]`

**Purpose:** Read stdout lines until the response matching request_id arrives.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.
5. Parse or serialize JSON payloads.
6. Spawn or communicate with a child process.

#### `def BrowserProcessManager._remember_result(result) -> None`

**Purpose:** Store the last non-blank URL from a tool result for idle restore.

#### `async def BrowserProcessManager._discard_process_locked(process, *, context, reason) -> None`

**Purpose:** Forget and stop a worker process whose pipes are no longer usable.

**Steps:**

1. Await async I/O or subprocess work.
2. Handle errors and map them to a safe response.
3. Spawn or communicate with a child process.

#### `def BrowserProcessManager._worker_response_is_retryable(response) -> bool`

**Purpose:** Return whether a worker error warrants spawning a fresh subprocess.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `async def BrowserProcessManager._send_tool_request_locked(process, tool_name, arguments, context, *, session, interval, message) -> dict[str, Any]`

**Purpose:** Write one tool request JSON line to the worker stdin and await its response.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Parse or serialize JSON payloads.
5. Spawn or communicate with a child process.

#### `def BrowserProcessManager._restored_refs_message(result) -> Any`

**Purpose:** Prepend a note that element refs are stale after worker restart.

**Steps:**

1. Return the computed result to the caller.

#### `async def BrowserProcessManager._restore_after_worker_restart_locked(process, tool_name, context, *, session, interval) -> Any | None`

**Purpose:** Re-navigate to the last URL after worker restart before retrying the tool.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Spawn or communicate with a child process.

---

## Related

- [mcp-browser-agent/_index](../../_index/)
