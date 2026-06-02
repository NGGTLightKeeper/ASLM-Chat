---
title: "browser"
draft: false
---

## Module `browser`

`Tools/mcp-browser-agent/browser.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-browser-agent`. See **Related** for package index and callers.

---

## Classes

### `class BrowserRuntime`

**Purpose:** Type `BrowserRuntime` defined in `browser.py`.

### `class BrowserState`

**Purpose:** Type `BrowserState` defined in `browser.py`.

---

## Public functions

#### `def BrowserRuntime.__init__() -> None`

**Purpose:** Initialize empty loop/thread handles for the dedicated browser event loop.

#### `def BrowserRuntime.ensure_started() -> None`

**Purpose:** Start the background loop thread when it is not already running.

#### `def BrowserRuntime.submit(coro) -> concurrent.futures.Future`

**Purpose:** Schedule a coroutine on the dedicated browser loop from any thread.

#### `def BrowserRuntime.close() -> None`

**Purpose:** Stop the dedicated browser loop after browser resources are closed.

#### `def close_browser_runtime() -> None`

**Purpose:** Stop the shared browser runtime loop during worker shutdown.

#### `async def run_in_browser_loop(coro, session, interval, message)`

**Purpose:** Run a browser coroutine on the dedicated browser loop with optional keepalive logs.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def get_accessibility_tree(page, full) -> tuple[list[dict], str]`

**Purpose:** Extract the current accessibility tree and assign stable element refs.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def is_browser_closed_error(exc) -> bool`

**Purpose:** Return whether an exception indicates the browser process or session died.

#### `def last_known_url() -> str`

**Purpose:** Return the most recent non-blank URL from the navigation history buffer.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def BrowserState.__init__()`

**Purpose:** Initialize empty browser, context, page, and tool context handles.

#### `def BrowserState.downloads_dir() -> Path`

**Purpose:** Return the active downloads directory for the current tool context.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `async def BrowserState.ensure_open() -> bool`

**Purpose:** Launch the browser lazily on first use; return True when a new session started.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Await async I/O or subprocess work.
4. Handle errors and map them to a safe response.
5. Spawn or communicate with a child process.

#### `async def BrowserState.close()`

**Purpose:** Close all shared browser resources and clear stored references.

**Steps:**

1. Await async I/O or subprocess work.
2. Handle errors and map them to a safe response.

#### `async def capture_portal_a11y_bundle(page, *, max_controls=…) -> dict | None`

**Purpose:** Build a compact a11y bundle for the live portal panel (throttled Playwright calls).

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def reset_portal_a11y_state() -> None`

**Purpose:** Reset portal a11y counters and bundle when a new portal session starts.

---

## Private functions

#### `def _load_local_config()`

**Purpose:** Load the sibling config module without relying on global sys.path order.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def BrowserRuntime._thread_main() -> None`

**Purpose:** Run the dedicated asyncio event loop on a background thread.

#### `def _is_noise_element(elem) -> bool`

**Purpose:** Return whether an element should be hidden from model-facing snapshot output.

**Steps:**

1. Return the computed result to the caller.

#### `def _snapshot_element_payload(el) -> dict[str, Any]`

**Purpose:** Return the stable, model-facing subset of one accessibility element.

**Steps:**

1. Return the computed result to the caller.

#### `def _format_control_line(el) -> str`

**Purpose:** Format one element as a compact markdown action line.

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

#### `def _filter_snapshot_controls(elements, *, full) -> list[dict]`

**Purpose:** Pick interactive controls that belong in the default snapshot.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _group_controls(elements) -> dict[str, list[dict]]`

**Purpose:** Group interactive elements by the operation a model can perform.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _format_parsed_controls(elements, *, full, max_items) -> list[str]`

**Purpose:** Format controls in a predictable grouped order for snapshot markdown.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_parsed_state(elements, *, full, max_items) -> dict[str, Any]`

**Purpose:** Build a compact structured state block for models that prefer JSON.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `async def _extract_brief_text(page, max_chars) -> str`

**Purpose:** Extract a short text preview from the main content area for full snapshots.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

#### `async def _wait_for_spa_content(page, timeout_ms)`

**Purpose:** Wait until SPA main content becomes readable without fixed sleeps.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def _auto_dismiss_overlays(page) -> list[str]`

**Purpose:** Try to dismiss common cookie banners and blocking popups before snapshotting.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def _detect_page_situation(page) -> list[str]`

**Purpose:** Detect CAPTCHA, login, cookie banner, and error-page situations for warnings.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def _detect_undismissable_overlay(page) -> str | None`

**Purpose:** Describe a blocking overlay that remains visible after auto-dismiss attempts.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

#### `async def BrowserState._has_live_page() -> bool`

**Purpose:** Return whether the stored Playwright page can still receive commands.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

#### `async def _take_snapshot(action_context, run_dismiss, include_text, full) -> list[TextContent]`

**Purpose:** Build the detailed page snapshot returned after navigation or major page changes.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `async def _take_compact_snapshot(action_context) -> list[TextContent]`

**Purpose:** Build the smaller controls-only snapshot used after in-page actions.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _find_element(ref) -> dict | None`

**Purpose:** Return the cached accessibility element matching the given ref.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `async def _resolve_locator(role, name)`

**Purpose:** Resolve the best Playwright locator for a role and accessible name pair.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def _click_by_role_and_name(ref)`

**Purpose:** Click a cached accessibility element using role/name resolution and fallbacks.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

---

## Related

- [mcp-browser-agent/_index](../../_index/)
