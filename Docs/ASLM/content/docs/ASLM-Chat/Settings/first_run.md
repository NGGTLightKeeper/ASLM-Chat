---
title: "first_run"
draft: false
---

## Module `first_run`

`Settings/first_run.py` — ASLM Chat Python module.

---

## Public functions

#### `def run(log, ui_port, api_port) -> None`

**Purpose:** Run the first-run setup workflow.

---

## Private functions

#### `def _build_initial_settings(existing, ui_port, api_port) -> dict[str, Any]`

**Purpose:** Build the initial settings payload for the first run.

**Steps:**

1. Return the computed result to the caller.

#### `def _print_warning(message) -> None`

**Purpose:** Print a standardized bootstrap warning.

#### `def _run_optional_command(command, *, description, log, cwd=…) -> bool`

**Purpose:** Run an optional bootstrap command without failing the full first-run setup.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Spawn or communicate with a child process.

#### `def _ensure_playwright_browsers(venv_id, log) -> None`

**Purpose:** Install Playwright browsers needed by the bundled tools.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _ensure_camoufox_binary(venv_id, log) -> None`

**Purpose:** Download the Camoufox browser binary when the venv is available.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _ensure_aslm_embedding_models(log) -> None`

**Purpose:** Download ASLM web-search embedding models from Hugging Face when missing.

#### `def _run_tool_bootstrap(log) -> None`

**Purpose:** Run post-dependency bootstrap tasks for bundled tools.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _print_summary(settings_file, initial) -> None`

**Purpose:** Print a short summary of the written first-run settings.

---

## Related

- [Settings/_index](../_index/)
