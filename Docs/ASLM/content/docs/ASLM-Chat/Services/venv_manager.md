---
title: "venv_manager"
draft: false
---

## Module `venv_manager`

`Services/venv_manager.py` — ASLM Chat Python module.

---

## Overview

Part of `Services`. See **Related** for package index and callers.

---

## Public functions

#### `def load_config() -> dict[str, Any]`

**Purpose:** Read venv requirements from Settings/venv_requirements.json.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def iter_venv_configs() -> list[dict[str, Any]]`

**Purpose:** Return normalized venv definitions from the requirements file.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def get_venv_config(venv_id) -> dict[str, Any] | None`

**Purpose:** Resolve one venv config by id.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def get_tool_venv_id(tool_dir_name) -> str`

**Purpose:** Resolve the venv id assigned to a tool directory name.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def get_venv_path(venv_id) -> Path`

**Purpose:** Return the absolute filesystem path for a configured venv.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def get_venv_python(venv_id) -> Path`

**Purpose:** Return the Python executable inside a configured venv.

**Steps:**

1. Return the computed result to the caller.

#### `def get_tool_python(tool_dir_name) -> Path | None`

**Purpose:** Return the tool venv Python executable when the tool is mapped in config.

**Steps:**

1. Return the computed result to the caller.

#### `def ensure_venv(venv_id, *, log=…) -> bool`

**Purpose:** Create or update one configured ASLM-Chat venv when packages changed.

**Steps:**

1. Return the computed result to the caller.

#### `def ensure_all(*, log=…) -> bool`

**Purpose:** Create or update every venv listed in the requirements file.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def run_venv_python(venv_id, args, *, log=…) -> bool`

**Purpose:** Run a Python command inside one configured venv.

**Steps:**

1. Return the computed result to the caller.

#### `def run_venv_code(venv_id, code, *, log=…) -> bool`

**Purpose:** Run a Python code snippet inside one configured venv.

---

## Private functions

#### `def _run(command, *, log, cwd=…) -> bool`

**Purpose:** Run one subprocess command and optionally stream output to the console.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Spawn or communicate with a child process.

#### `def _packages_signature(packages, packages_no_deps) -> str`

**Purpose:** Compute a stable hash for one venv package manifest.

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

#### `def _read_state(venv_path) -> dict[str, Any]`

**Purpose:** Read persisted install state for one venv directory.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _write_state(venv_path, packages, packages_no_deps) -> None`

**Purpose:** Persist the package signature after a successful install.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def _create_venv(venv_id, log) -> bool`

**Purpose:** Create a Python virtual environment for one configured venv id.

**Steps:**

1. Return the computed result to the caller.

#### `def _pip_install(python_path, packages, *, no_deps, log, label) -> bool`

**Purpose:** Install one package list into a venv via pip.

**Steps:**

1. Return the computed result to the caller.

#### `def _install_packages(venv_id, packages, packages_no_deps, log) -> bool`

**Purpose:** Install regular and no-deps package lists for one venv id.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [Services/_index](../_index/)
