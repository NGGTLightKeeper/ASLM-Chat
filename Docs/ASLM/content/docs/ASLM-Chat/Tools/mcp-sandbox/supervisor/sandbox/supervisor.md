---
title: "supervisor"
draft: false
---

## Module `supervisor`

`Tools/mcp-sandbox/supervisor/sandbox/supervisor.py` — ASLM Chat Python module.

---

## Public functions

#### `def main() -> None`

**Purpose:** Start FastMCP with sandbox tools (or healthcheck when requested).

---

## Private functions

#### `def _prefer_supervisor_source() -> None`

**Purpose:** Prefer the read-only source bind when the image also has a copy.

#### `def _protect_from_oom() -> None`

**Purpose:** Best-effort supervisor OOM protection.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def _set_process_title() -> None`

**Purpose:** Use a stable process title when setproctitle is available.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def _cleanup_orphaned_job_dirs() -> None`

**Purpose:** Kill and remove job dirs left from previous supervisor sessions.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

---

## Related

- [sandbox/_index](../../../../_index/)
