---
title: "docker_host"
draft: false
---

## Module `docker_host`

`Tools/mcp-sandbox/src/sandbox/docker_host.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-sandbox\src\sandbox`. See **Related** for package index and callers.

---

## Public functions

#### `def restart_container() -> tuple[bool, str]`

**Purpose:** Implements `restart_container` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def snapshot_image_name(name) -> str`

**Purpose:** Implements `snapshot_image_name` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def snapshot_container(name, *, preflight=…) -> dict`

**Purpose:** Implements `snapshot_container` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def start_container_supervisor() -> subprocess.Popen`

**Purpose:** Implements `start_container_supervisor` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.
2. Spawn or communicate with a child process.

#### `def healthcheck_container_supervisor(timeout_s) -> tuple[bool, str]`

**Purpose:** Implements `healthcheck_container_supervisor` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Spawn or communicate with a child process.

#### `def ensure_supervisor_ready(*, attempts=…, timeout_s=…, recreate_on_failure=…) -> tuple[bool, str]`

**Purpose:** Implements `ensure_supervisor_ready` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def pipe_to_container_supervisor(*, max_restarts=…, input_stream=…, output_stream=…, error_stream=…) -> int`

**Purpose:** Pipe host stdio to the in-container MCP supervisor with reconnect.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def list_background_jobs() -> dict`

**Purpose:** Implements `list_background_jobs` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def foreground_background_job(job_id) -> dict`

**Purpose:** Implements `foreground_background_job` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def kill_background_job(job_id) -> dict`

**Purpose:** Implements `kill_background_job` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def get_status() -> dict`

**Purpose:** Return Docker and container status without forcing startup.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

---

## Private functions

#### `def _rewrite_legacy_upload_paths(command) -> str`

**Purpose:** Keep old model-facing upload paths usable in plain bash commands.

#### `def _resolve_docker_job_root() -> str`

**Purpose:** Pick a container-writable root for background spool files.

**Steps:**

1. Return the computed result to the caller.

#### `def _docker_job_root_candidates() -> list[str]`

**Purpose:** Return ordered job-root candidates for docker background jobs.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _run_command(args, timeout, check, input_text)`

**Purpose:** Run a subprocess command with UTF-8 text handling.

**Steps:**

1. Return the computed result to the caller.
2. Spawn or communicate with a child process.

#### `def _docker_cli_available() -> bool`

**Purpose:** Return True when the docker CLI is installed.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _docker_info(timeout)`

**Purpose:** Query docker daemon info.

#### `def _auto_start_docker_enabled() -> bool`

**Purpose:** Return whether host tools may launch Docker Desktop automatically.

#### `def _ensure_docker_running() -> tuple[bool, str]`

**Purpose:** Ensure the Docker daemon is available.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Spawn or communicate with a child process.

#### `def _container_exists() -> bool`

**Purpose:** Container existence checks

**Steps:**

1. Return the computed result to the caller.

#### `def _image_has_required_runtime(inspect_stdout) -> bool`

**Purpose:** Image preparation

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _ensure_image(force_rebuild) -> tuple[bool, str]`

**Purpose:** Ensure the sandbox image exists locally by delegating to setup-sandbox.py.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.
3. Spawn or communicate with a child process.

#### `def _linux_venv_bind_source() -> str | None`

**Purpose:** Container run command

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def _ensure_sandbox_config(config_path) -> None`

**Purpose:** Create sandbox.env with commented-out defaults if it does not exist yet.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def _build_run_command(image_name, include_storage_limit) -> list[str]`

**Purpose:** Build the docker run command for the sandbox container.

**Steps:**

1. Return the computed result to the caller.

#### `def _ensure_container_running(image_name, max_retries, retry_delay) -> tuple[bool, str]`

**Purpose:** Ensure the sandbox container is running (idempotent with retry).

**Steps:**

1. Return the computed result to the caller.

#### `def _ensure_container_locked(image_name, max_retries, retry_delay) -> tuple[bool, str]`

**Purpose:** Implements `_ensure_container_locked` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _inspect_container() -> dict | None`

**Purpose:** Implements `_inspect_container` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _force_remove() -> tuple[bool, str]`

**Purpose:** Implements `_force_remove` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def _start_existing() -> tuple[bool, str]`

**Purpose:** Implements `_start_existing` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def _storage_limit_unsupported(stderr_text) -> bool`

**Purpose:** Implements `_storage_limit_unsupported` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _create_container(image_name) -> tuple[bool, str]`

**Purpose:** Implements `_create_container` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _wait_for_container_running(timeout_s) -> tuple[bool, str]`

**Purpose:** Poll until the container reaches 'running' state or the timeout expires.  Returns False if the container enters a restart loop (crashes immediately) so the caller can report a meaningful error rather than getting a confusing 'Container is restarting' error from docker exec.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _snapshot_check_result(name, ok, *, message=…, details=…) -> dict`

**Purpose:** Implements `_snapshot_check_result` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def _run_snapshot_preflight() -> dict`

**Purpose:** Run safety/stability checks before mutating Docker snapshot state.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def _supervisor_exec_command(*, interactive=…, supervisor_args=…) -> list[str]`

**Purpose:** Supervisor stdio proxy

**Steps:**

1. Return the computed result to the caller.

#### `def _supervisor_python_missing(message) -> bool`

**Purpose:** Implements `_supervisor_python_missing` in `docker_host.py`.

#### `def _read_pipe_chunk(source) -> bytes`

**Purpose:** Implements `_read_pipe_chunk` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def _forward_binary_stream(source, sink, close_sink) -> None`

**Purpose:** Implements `_forward_binary_stream` in `docker_host.py`.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def _read_stdin_to_queue(input_stream, input_queue, eof) -> None`

**Purpose:** Implements `_read_stdin_to_queue` in `docker_host.py`.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _write_queue_to_process(input_queue, process, eof) -> None`

**Purpose:** Implements `_write_queue_to_process` in `docker_host.py`.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.
3. Spawn or communicate with a child process.

#### `def _docker_exec_shell(script, *, container_cwd=…, timeout=…, user=…)`

**Purpose:** ── Docker-exec bash backend (host-side fallback) ──────────────────── Used when IN_CONTAINER=False. Will be removed after full migration.

**Steps:**

1. Return the computed result to the caller.

#### `def _read_docker_job_file(job, stream, *, incremental=…) -> str`

**Purpose:** Implements `_read_docker_job_file` in `docker_host.py`.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def _refresh_docker_job(job) -> BackgroundJob`

**Purpose:** Implements `_refresh_docker_job` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _exec_bash_docker_background(command, cwd, timeout_s, container_cwd, on_progress) -> dict`

**Purpose:** Implements `_exec_bash_docker_background` in `docker_host.py`.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _exec_bash_docker(command, cwd, timeout_s, stdin, on_stdout, on_stderr, on_progress, background) -> dict`

**Purpose:** Execute a bash command inside the sandbox container via docker exec.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.
5. Spawn or communicate with a child process.

---

## Related

- [sandbox/_index](../../../../_index/)
