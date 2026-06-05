---
title: "container"
draft: false
---

## Module `container`

`Tools/mcp-sandbox/supervisor/sandbox/container.py` — ASLM Chat Python module.

---

## Public functions

#### `def list_background_jobs() -> dict`

**Purpose:** List background jobs; refresh native running jobs whose process has exited.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def foreground_background_job(job_id) -> dict`

**Purpose:** Poll a background job and return incremental stdout/stderr since last read.

**Steps:**

1. Return the computed result to the caller.

#### `def kill_background_job(job_id) -> dict`

**Purpose:** Terminate a running background job's process group, then mark it killed.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

---

## Related

- [sandbox/_index](../../../../_index/)
