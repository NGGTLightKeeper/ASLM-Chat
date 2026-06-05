---
title: "main"
draft: false
---

## Module `main`

`main.py` — ASLM Chat Python module.

---

## Overview

ASLM host CLI: re-exec into server venv, Django management commands, Ollama service control, downloads bridge.


---

## Classes

### `class LazyDjangoApplication`

**Purpose:** Bind the UI port first, then hand requests to Django once it is ready.

---

## Public functions

#### `def run_django_command(*args, log=…) -> None`

**Purpose:** Execute a Django management command.

#### `def LazyDjangoApplication.__init__() -> None`

**Purpose:** Implements `LazyDjangoApplication.__init__` in `main.py`.

#### `def LazyDjangoApplication.load_in_background() -> None`

**Purpose:** Start loading Django without blocking the listening socket.

#### `def LazyDjangoApplication.__call__(environ, start_response)`

**Purpose:** Implements `LazyDjangoApplication.__call__` in `main.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def cmd_runserver(port, log) -> None`

**Purpose:** Start the Django development server on the requested port.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def cmd_migrate(log) -> None`

**Purpose:** Apply all pending database migrations.

#### `def cmd_makemigrations(app, log) -> None`

**Purpose:** Create migration files for changed models.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def cmd_collectstatic(log) -> None`

**Purpose:** Collect static files into ``STATIC_ROOT``.

#### `def cmd_first_run(log, ui_port, api_port) -> None`

**Purpose:** Generate settings and apply initial migrations.

#### `def cmd_get_setting(key) -> None`

**Purpose:** Print a single setting value for ASLM integration hooks.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def cmd_set_setting(key, value) -> None`

**Purpose:** Update a single setting key from string input.

#### `def cmd_apply_aslm_host_theme(theme_file) -> None`

**Purpose:** Apply a JSON theme snapshot written by ASLM (temp file path in ``--file``).

**Steps:**

1. Handle errors and map them to a safe response.
2. Parse or serialize JSON payloads.

#### `def cmd_apply_aslm_locale(locale_file) -> None`

**Purpose:** Apply a JSON locale snapshot written by ASLM (temp file path in ``--file``).

**Steps:**

1. Handle errors and map them to a safe response.
2. Parse or serialize JSON payloads.

#### `def maybe_start_local_engine_service(log) -> None`

**Purpose:** Start the active local engine service when the current adapter needs it.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def cmd_ollama_runtime(log) -> None`

**Purpose:** Run the dedicated managed Ollama runtime as its own tracked process.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def cmd_downloads_bridge() -> None`

**Purpose:** Read one downloads bridge JSON request from stdin and print the JSON response.

**Steps:**

1. Raise on invalid input or failure conditions.

#### `def main() -> None`

**Purpose:** Parse CLI arguments and dispatch the requested command.

**Steps:**

1. Iterate and transform or accumulate state.

---

## Private functions

#### `def _maybe_reexec_in_server_venv(command) -> None`

**Purpose:** Delegate the current command to ASLM-Chat's server venv when required.

**Steps:**

1. Handle errors and map them to a safe response.
2. Spawn or communicate with a child process.

#### `def LazyDjangoApplication._load() -> None`

**Purpose:** Implements `LazyDjangoApplication._load` in `main.py`.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def _build_parser() -> argparse.ArgumentParser`

**Purpose:** Return the command-line parser for the project entry point.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _maybe_print_banner(command) -> None`

**Purpose:** Print technical module data once for interactive commands.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _resolve_runserver_port(requested_port) -> int`

**Purpose:** Return the effective UI port for ``runserver``.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

---

## Related

- [ASLM-Chat/_index](../_index/)
