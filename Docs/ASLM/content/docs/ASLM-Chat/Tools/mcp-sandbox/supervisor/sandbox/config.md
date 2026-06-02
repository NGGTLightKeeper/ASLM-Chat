---
title: "config"
draft: false
---

## Module `config`

`Tools/mcp-sandbox/supervisor/sandbox/config.py` — ASLM Chat Python module.

---

## Public functions

#### `def get_allowed_import_roots() -> list[str]`

**Purpose:** Return normalized host roots allowed for imports.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _load_sandbox_env(path) -> None`

**Purpose:** Load sandbox.env into os.environ (does not overwrite vars already set).

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def _load_rg_type_map() -> dict[str, str]`

**Purpose:** Return ripgrep type aliases mapped to representative glob patterns.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Spawn or communicate with a child process.

#### `def _validate_workspace_path(path) -> bool`

**Purpose:** Return True when the host workspace path looks safe.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [sandbox/_index](../../../../_index/)
