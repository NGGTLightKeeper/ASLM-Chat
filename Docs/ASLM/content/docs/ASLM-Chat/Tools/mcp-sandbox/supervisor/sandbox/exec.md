---
title: "exec"
draft: false
---

## Module `exec`

`Tools/mcp-sandbox/supervisor/sandbox/exec.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-sandbox\supervisor\sandbox`. See **Related** for package index and callers.

---

## Classes

### `class BoundedOutputCollector`

**Purpose:** Type `BoundedOutputCollector` defined in `exec.py`.

---

## Public functions

#### `def BoundedOutputCollector.__init__() -> None`

**Purpose:** Implements `BoundedOutputCollector.__init__` in `exec.py`.

#### `def BoundedOutputCollector.append(chunk) -> None`

**Purpose:** Implements `BoundedOutputCollector.append` in `exec.py`.

#### `def BoundedOutputCollector.value() -> tuple[str, bool]`

**Purpose:** Implements `BoundedOutputCollector.value` in `exec.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def should_use_background(command, timeout_s, background) -> bool`

**Purpose:** Decide whether a command should run as a tracked background job.

**Steps:**

1. Return the computed result to the caller.

#### `def job_root() -> Path`

**Purpose:** Ensure JOB_ROOT exists and return its Path.

---

## Private functions

#### `def _slice_utf8(data, start, end) -> str`

**Purpose:** Shared output helpers

#### `def _truncate(value) -> tuple[str, bool]`

**Purpose:** Trim output to a configurable head/tail window with an inline marker.

**Steps:**

1. Return the computed result to the caller.

#### `def _read_stream_chunks(stream, sink, callback) -> None`

**Purpose:** Read process output in chunks and forward each chunk to an optional callback.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _normalize_background_mode(background) -> str`

**Purpose:** Map bool/None background flag to auto | always | never.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def _new_background_job_id() -> str`

**Purpose:** Implements `_new_background_job_id` in `exec.py`.

#### `def _background_error_result(*, job, stdout, stderr, start_time, timeout_s, cwd, truncated=…) -> dict`

**Purpose:** Bash-shaped dict when foreground wait hits timeout but the job keeps running.

**Steps:**

1. Return the computed result to the caller.

#### `def _job_files_result(job, *, incremental=…) -> tuple[str, str, bool]`

**Purpose:** Read and truncate background job spool files (stdout/stderr).

**Steps:**

1. Return the computed result to the caller.

#### `def _popen_user_kwargs() -> dict`

**Purpose:** POSIX-only Popen user-switching options when supervisor runs as root.

**Steps:**

1. Return the computed result to the caller.

#### `def _command_user_env() -> dict[str, str]`

**Purpose:** Environment overrides (HOME, USER, SHELL) for the model command user.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _kill_process_group(process) -> None`

**Purpose:** Best-effort SIGTERM then SIGKILL for the command's process group.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.
3. Spawn or communicate with a child process.

#### `def _wait_after_kill(process, timeout) -> None`

**Purpose:** Block until the process exits after a kill (best-effort).

**Steps:**

1. Handle errors and map them to a safe response.
2. Spawn or communicate with a child process.

#### `def _exec_bash_native_background(command, cwd, timeout_s, stdin, on_progress) -> dict`

**Purpose:** Run bash with output spooled to disk; may return early as a background job.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.
5. Spawn or communicate with a child process.

#### `def _exec_bash_native(command, cwd, timeout_s, stdin, on_stdout, on_stderr, on_progress, background) -> dict`

**Purpose:** Execute bash in-process with piped stdout/stderr and optional background routing.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.
5. Spawn or communicate with a child process.

---

## Related

- [sandbox/_index](../../../../_index/)
