---
title: "controller"
draft: false
---

## Module `controller`

`Tools/mcp-sandbox/supervisor/sandbox/controller.py` — ASLM Chat Python module.

---

## Public functions

#### `def dispatch(command, cwd, state, make_bash_success, make_bash_error) -> dict[str, Any] | None`

**Purpose:** Classify command and dispatch; None means fall through to real bash.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

---

## Private functions

#### `def _handle_open(nc, state, cwd) -> dict[str, Any]`

**Purpose:** OPEN intent: read file content with loop-breaking and preview fallbacks.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _handle_locate(nc, state, cwd) -> dict[str, Any]`

**Purpose:** LOCATE intent: grep-style search via workspace.grep and presenter.

**Steps:**

1. Return the computed result to the caller.

#### `def _handle_survey(nc, state, cwd) -> dict[str, Any]`

**Purpose:** SURVEY intent (ls/tree): directory listing with optional survey cache.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _handle_find(nc, state, cwd) -> dict[str, Any]`

**Purpose:** SURVEY intent (find/fd): find files by name/type via workspace.find.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_preview(path, meta, size) -> str`

**Purpose:** Build structured head/tail preview for large or long files.

**Steps:**

1. Return the computed result to the caller.

#### `def _ok(stdout, path, warnings) -> dict[str, Any]`

**Purpose:** Internal success shape before conversion to bash response.

**Steps:**

1. Return the computed result to the caller.

#### `def _err(message) -> dict[str, Any]`

**Purpose:** Internal error shape before conversion to bash response.

**Steps:**

1. Return the computed result to the caller.

#### `def _not_found(message) -> None`

**Purpose:** Signal path errors so _try_supervise can fall back to real bash.

---

## Related

- [sandbox/_index](../../../../_index/)
