---
title: "ollama-service"
draft: false
---

## Module `ollama-service`

`Services/ollama-service.py` — ASLM Chat Python module.

---

## Overview

Part of `Services`. See **Related** for package index and callers.

---

## Classes

### `class OllamaDesiredState`

**Purpose:** Type `OllamaDesiredState` defined in `ollama-service.py`.

---

## Public functions

#### `def start_ollama(engine) -> bool`

**Purpose:** Start the local Ollama service when the active engine requires it.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Spawn or communicate with a child process.

#### `def run_ollama_runtime(log) -> int`

**Purpose:** Replace the current process with ollama serve for the dedicated runtime command.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def stop_ollama() -> None`

**Purpose:** Stop the managed Ollama service when a tracked PID exists.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.
3. Spawn or communicate with a child process.

#### `def run_ollama_console(log) -> None`

**Purpose:** Stream the managed Ollama log file into stdout for the console command.

---

## Private functions

#### `def _read_pid() -> int | None`

**Purpose:** Read the managed Ollama PID from disk.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _write_pid(pid) -> None`

**Purpose:** Persist the managed Ollama PID on disk.

#### `def _clear_pid() -> None`

**Purpose:** Remove the saved Ollama PID file.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def _is_pid_running(pid) -> bool`

**Purpose:** Return whether the given PID still points to a live process.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _get_desired_state(requested_engine) -> OllamaDesiredState`

**Purpose:** Resolve whether the managed Ollama runtime should currently be running.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_service_environment() -> tuple[dict[str, str], int]`

**Purpose:** Build environment variables used to launch the managed Ollama service.

**Steps:**

1. Return the computed result to the caller.

#### `def _sanitize_console_line(message) -> str`

**Purpose:** Strip ANSI escapes and trailing line breaks for ASLM console rendering.

#### `def _truncate_console_line(message, limit) -> str`

**Purpose:** Trim long console lines so ASLM stays readable.

**Steps:**

1. Return the computed result to the caller.

#### `def _parse_structured_log_fields(message) -> dict[str, str]`

**Purpose:** Parse Ollama key=value log lines into a dictionary.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _extract_env_value(env_blob, env_key) -> str`

**Purpose:** Extract one environment variable from Ollama's server-config log dump.

**Steps:**

1. Return the computed result to the caller.

#### `def _collect_remaining_field_details(fields, *, excluded_keys=…, max_items=…) -> list[str]`

**Purpose:** Format extra structured-log fields as key=value details.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _summarize_load_request(request_blob) -> list[str]`

**Purpose:** Extract useful runner load-request fields from Ollama trace lines.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _format_gin_line(message) -> str | None`

**Purpose:** Convert GIN access logs into a compact summary.

**Steps:**

1. Return the computed result to the caller.

#### `def _format_backend_line(message) -> str`

**Purpose:** Convert backend loader logs into a shorter summary.

**Steps:**

1. Return the computed result to the caller.

#### `def _format_structured_ollama_line(message) -> str | None`

**Purpose:** Convert Ollama structured logs into concise console lines.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _format_console_log_line(message) -> str | None`

**Purpose:** Convert raw Ollama output into a readable console line.

**Steps:**

1. Return the computed result to the caller.

#### `def _print_status(message) -> None`

**Purpose:** Emit one watcher status line to stdout.

#### `def _read_recent_log_lines(limit) -> list[str]`

**Purpose:** Return the latest non-empty lines from the managed Ollama log file.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _stream_new_log_lines(position) -> int`

**Purpose:** Print managed Ollama log lines written after the given file offset.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _stream_log_file_forever() -> None`

**Purpose:** Mirror managed Ollama log lines into the current process stdout.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def _ensure_log_streaming() -> None`

**Purpose:** Start a single background thread that forwards Ollama logs to stdout.

#### `def _wait_until_ready(timeout_seconds) -> bool`

**Purpose:** Wait until the local Ollama HTTP endpoint starts responding.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _wait_for_existing_runtime(timeout_seconds) -> bool`

**Purpose:** Give a separately launched Ollama runtime a short chance to appear.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _is_running_inside_aslm() -> bool`

**Purpose:** Return whether ASLM module infrastructure launched the current process.

---

## Related

- [Services/_index](../_index/)
