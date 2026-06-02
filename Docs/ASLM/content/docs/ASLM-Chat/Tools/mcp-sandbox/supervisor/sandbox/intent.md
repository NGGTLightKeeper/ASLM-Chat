---
title: "intent"
draft: false
---

## Module `intent`

`Tools/mcp-sandbox/supervisor/sandbox/intent.py` — ASLM Chat Python module.

---

## Classes

### `class Intent`

**Purpose:** Type `Intent` defined in `intent.py`.

### `class NormalizedCommand`

**Purpose:** Type `NormalizedCommand` defined in `intent.py`.

---

## Public functions

#### `def classify(command, cwd) -> NormalizedCommand | None`

**Purpose:** Classify a shell command; None means fall through to real bash.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _safe_split(s) -> list[str]`

**Purpose:** Shell-safe tokenization; fall back to whitespace split on parse errors.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _is_container_path(path) -> bool`

**Purpose:** True for absolute paths outside task-space (e.g. /etc); task paths are routed.

**Steps:**

1. Return the computed result to the caller.

#### `def _split_pipeline(command) -> list[str] | None`

**Purpose:** Split on | only; None when &&, ||, ;, subshells, or redirections are present.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _classify_single_command(cmd) -> Intent | None`

**Purpose:** Map a bare command name to Intent, or None if unknown (→ RUN).

**Steps:**

1. Return the computed result to the caller.

#### `def _parse_open_args(cmd, args) -> dict[str, Any]`

**Purpose:** Extract target path, line range, and unsupported-flag marker from OPEN commands.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _parse_locate_args(cmd, args) -> dict[str, Any]`

**Purpose:** Extract pattern, search path, glob, context, and flags from LOCATE commands.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _parse_survey_args(cmd, args) -> dict[str, Any]`

**Purpose:** Extract path, depth, hidden/name/type flags from SURVEY (ls/tree/find) commands.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _normalize_pipeline(stages, cwd) -> NormalizedCommand | None`

**Purpose:** Collapse read-only pipe chains into one NormalizedCommand; None if unsafe.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

---

## Related

- [sandbox/_index](../../../../_index/)
