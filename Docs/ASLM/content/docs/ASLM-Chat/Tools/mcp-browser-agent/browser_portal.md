---
title: "browser_portal"
draft: false
---

## Module `browser_portal`

`Tools/mcp-browser-agent/browser_portal.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-browser-agent`. See **Related** for package index and callers.

---

## Public functions

#### `def append_browser_portal_debug_event(context, event, **fields) -> None`

**Purpose:** Browser portal debug logging is intentionally disabled.

**Steps:**

1. Return the computed result to the caller.

#### `async def capture_browser_portal_frame(page) -> dict[str, Any] | None`

**Purpose:** Capture a small JPEG viewport frame for the chat browser portal.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

#### `def browser_portal_root(context) -> Path`

**Purpose:** Resolve the on-disk root directory for portal state and events.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def browser_portal_events_dir(context) -> Path`

**Purpose:** Return the directory where portal UI events are queued.

#### `def browser_portal_state_path(context) -> Path`

**Purpose:** Return the path to the portal state.json file.

#### `def reset_browser_portal_state(context, *, message, timeout_seconds) -> str`

**Purpose:** Reset portal session files and write initial waiting state; return new session_id.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def read_browser_portal_state(context) -> dict[str, Any]`

**Purpose:** Read and parse the current portal state.json payload.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def enqueue_browser_portal_event(payload, context) -> dict[str, Any]`

**Purpose:** Write one UI event JSON file into the portal events directory.

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

#### `async def publish_browser_portal_frame(page, context, *, status=…, message=…, timeout_seconds=…, session_id=…) -> dict[str, Any]`

**Purpose:** Capture frame and a11y bundle and merge them into portal state.json.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

#### `async def apply_browser_portal_events(page, context, *, session_id=…) -> bool`

**Purpose:** Apply queued portal UI events (click, scroll, key, type, click_ref) to the page.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def with_browser_portal_ui(result, *, tool_name, arguments, page) -> Any`

**Purpose:** Wrap a text tool result with UI metadata without changing model-facing text.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

---

## Private functions

#### `def _get_browser_mod()`

**Purpose:** Lazy-import browser module to avoid circular imports at module load time.

**Steps:**

1. Return the computed result to the caller.

#### `def _status_from_result(result) -> str`

**Purpose:** Map a tool result string to a portal UI status (done, failed, waiting).

**Steps:**

1. Return the computed result to the caller.

#### `def _write_portal_state(context, payload, *, session_id=…) -> bool`

**Purpose:** Atomically write portal state.json with optional session_id guard.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.
5. Parse or serialize JSON payloads.

#### `def _pop_browser_portal_events(context, *, session_id=…) -> list[dict[str, Any]]`

**Purpose:** Read and remove queued portal events, optionally filtered by session_id.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

---

## Related

- [mcp-browser-agent/_index](../../_index/)
