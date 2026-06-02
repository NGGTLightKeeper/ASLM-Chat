---
title: "cleanup"
draft: false
---

## Module `cleanup`

`Tools/mcp-sandbox/supervisor/sandbox/cleanup.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-sandbox\supervisor\sandbox`. See **Related** for package index and callers.

---

## Public functions

#### `def stage_workspace_to_tmp(staged_at) -> Path | None`

**Purpose:** Move current root entries into one tmp batch inside the sandbox.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def recycle_due_tmp_batches(now) -> list[Path]`

**Purpose:** Move expired tmp batches to the OS trash without depending on trash name.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def run_cleanup_once() -> None`

**Purpose:** Perform one cleanup pass if the sandbox is idle.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def ensure_cleanup_monitor_started() -> None`

**Purpose:** Start the daemon cleanup monitor thread once per process.

#### `def sandbox_tool_activity() -> Iterator[None]`

**Purpose:** Implements `sandbox_tool_activity` in `cleanup.py`.

---

## Private functions

#### `def _utc_now() -> datetime`

**Purpose:** Current UTC time.

#### `def _iso_now() -> str`

**Purpose:** ISO-8601 timestamp for the current instant.

#### `def _parse_iso_timestamp(value) -> datetime | None`

**Purpose:** Parse an ISO timestamp string, or return None when invalid.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _safe_batch_name() -> str`

**Purpose:** Generate a unique batch directory name under tmp/.

#### `def _unique_child(parent, name) -> Path`

**Purpose:** Pick a non-colliding child path under parent.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _write_json(path, payload) -> None`

**Purpose:** Atomically write JSON metadata to path.

#### `def _read_json(path) -> dict[str, object]`

**Purpose:** Read JSON metadata from path (empty dict on failure).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _remember_cleanup_event(root, event, **details) -> None`

**Purpose:** Persist the latest cleanup event for observability.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def _iter_stageable_root_entries(root) -> list[Path]`

**Purpose:** List task-root entries eligible for idle staging (excluding reserved names).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _has_running_background_jobs() -> bool`

**Purpose:** Return True when any registered background job is still running.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _safe_tmp_root(root) -> Path`

**Purpose:** Ensure tmp/ exists under task root and cannot escape via symlinks.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.

#### `def _batch_staged_at(batch_dir) -> datetime | None`

**Purpose:** Resolve when a tmp batch was staged (metadata or directory mtime).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _send_to_windows_recycle_bin(path) -> None`

**Purpose:** Send a path to the Windows recycle bin via SHFileOperationW.

**Steps:**

1. Raise on invalid input or failure conditions.

#### `def _send_to_platform_trash(path) -> None`

**Purpose:** Send a path to the platform trash (Windows, send2trash, or gio).

**Steps:**

1. Raise on invalid input or failure conditions.
2. Handle errors and map them to a safe response.
3. Spawn or communicate with a child process.

#### `def _monitor_loop() -> None`

**Purpose:** Background loop that periodically runs idle workspace cleanup.

**Steps:**

1. Iterate and transform or accumulate state.

---

## Related

- [sandbox/_index](../../../../_index/)
