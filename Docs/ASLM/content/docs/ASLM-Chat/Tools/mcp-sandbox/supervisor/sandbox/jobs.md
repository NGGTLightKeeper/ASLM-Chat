---
title: "jobs"
draft: false
---

## Module `jobs`

`Tools/mcp-sandbox/supervisor/sandbox/jobs.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-sandbox\supervisor\sandbox`. See **Related** for package index and callers.

---

## Classes

### `class BackgroundJob`

**Purpose:** Type `BackgroundJob` defined in `jobs.py`.

### `class JobRegistry`

**Purpose:** Type `JobRegistry` defined in `jobs.py`.

---

## Public functions

#### `def BackgroundJob.to_result() -> dict[str, Any]`

**Purpose:** Implements `BackgroundJob.to_result` in `jobs.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def JobRegistry.__init__() -> None`

**Purpose:** Implements `JobRegistry.__init__` in `jobs.py`.

#### `def JobRegistry.create(*, command, cwd, runtime, pid=…, host_job_dir=…, container_job_dir=…, process=…, job_id=…) -> BackgroundJob`

**Purpose:** Implements `JobRegistry.create` in `jobs.py`.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def JobRegistry.get(job_id) -> BackgroundJob`

**Purpose:** Implements `JobRegistry.get` in `jobs.py`.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def JobRegistry.list_jobs() -> list[dict[str, Any]]`

**Purpose:** Implements `JobRegistry.list_jobs` in `jobs.py`.

#### `def JobRegistry.remove(job_id, *, cleanup=…) -> BackgroundJob | None`

**Purpose:** Implements `JobRegistry.remove` in `jobs.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def JobRegistry.read_output(job_id, stream, *, incremental=…) -> str`

**Purpose:** Implements `JobRegistry.read_output` in `jobs.py`.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def JobRegistry.mark_done(job_id, exit_code) -> BackgroundJob`

**Purpose:** Implements `JobRegistry.mark_done` in `jobs.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def JobRegistry.mark_killed(job_id) -> BackgroundJob`

**Purpose:** Implements `JobRegistry.mark_killed` in `jobs.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def JobRegistry.purge_stale(ttl_seconds) -> int`

**Purpose:** Remove finished jobs older than ttl_seconds; returns count removed.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def JobRegistry.reset() -> None`

**Purpose:** Implements `JobRegistry.reset` in `jobs.py`.

---

## Private functions

#### `def JobRegistry._read_bounded_text(path, *, start=…) -> tuple[str, int]`

**Purpose:** Read a slice of a spool file with head/tail truncation when over MAX_OUTPUT_BYTES.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def JobRegistry._new_job_id() -> str`

**Purpose:** Implements `JobRegistry._new_job_id` in `jobs.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [sandbox/_index](../../../../_index/)
