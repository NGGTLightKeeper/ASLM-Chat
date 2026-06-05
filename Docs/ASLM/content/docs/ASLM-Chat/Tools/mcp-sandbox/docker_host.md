---
title: "docker_host"
draft: false
---

## Module `docker_host`

`Tools/mcp-sandbox/src/sandbox/docker_host.py` — Host-side Docker integration when the MCP process runs outside the container.

---

## Overview

On the host, [mcp-server](mcp-server/) replaces in-container `exec_bash` and job helpers with this module so ASLM never spawns bash on Windows directly. Responsibilities:

- **Lifecycle** — Ensure image (label `container-v2`), create/start container, optional snapshots and reset.
- **Supervisor pipe** — [server](server/) forwards stdio to `python -m sandbox.supervisor` inside the container.
- **Bash** — Sync and background jobs via `docker exec`, with spool files under container job dirs mirrored in [jobs](supervisor/sandbox/jobs/) on the host.
- **Status** — `get_status()` reports daemon, container, and workspace without forcing a start.

---

## Functions — path and job roots

| Function | Purpose |
| --- | --- |
| `_rewrite_legacy_upload_paths(command)` | Replace `/mnt/data/User` with workspace `User` path in commands |
| `_resolve_docker_job_root()` | Container-writable directory for background spool files |
| `_docker_job_root_candidates()` | Ordered fallback paths when primary job root fails |

---

## Docker CLI

| Function | Purpose |
| --- | --- |
| `_run_command(args, timeout)` | Subprocess with UTF-8 text capture |
| `_docker_cli_available()` | `docker` on PATH |
| `_docker_info(timeout)` | `docker info` JSON |
| `_auto_start_docker_enabled()` | Read `SANDBOX_AUTO_START_DOCKER` |
| `_ensure_docker_running()` | Start Docker Desktop on Windows when configured; verify daemon |

---

## Container lifecycle

| Function | Purpose |
| --- | --- |
| `_container_exists()` | Named container present |
| `_container_is_running()` | Container state `running` |
| `_image_has_required_runtime(inspect_stdout)` | Label `org.aslm.sandbox.supervisor-runtime=container-v2` |
| `_ensure_image(force_rebuild)` | Pull/build image when missing or invalid |
| `_linux_venv_bind_source()` | Host venv path to mount for supervisor Python |
| `_ensure_sandbox_config(config_path)` | Ensure `sandbox.env` exists before run |
| `_build_run_command(...)` | Assemble `docker run` with limits, binds, env |
| `_ensure_container_running()` | Public ensure: image + container up |
| `_ensure_container_locked()` | Locked variant with recreate/retry logic |
| `_inspect_container()` | Parse `docker inspect` JSON |
| `_force_remove()` | Remove container forcefully |
| `_start_existing()` | `docker start` existing container |
| `_storage_limit_unsupported(stderr)` | Detect unsupported `--storage-opt` |
| `_create_container(image_name)` | `docker run -d` create |
| `_wait_for_container_running(timeout_s)` | Poll until running |
| `restart_container()` | Restart named container |
| `remove_container()` | Stop and remove |

---

## Snapshots and preflight

| Function | Purpose |
| --- | --- |
| `snapshot_image_name(name)` | Tag for `CONTAINER_NAME-snapshot-{name}` |
| `_snapshot_check_result(...)` | Build preflight check record |
| `_run_snapshot_preflight()` | Smoke tests inside container before commit |
| `snapshot_container(name, preflight=True)` | Commit running container to snapshot image |
| `reset_container(preserve_workspace)` | Recreate container; optional workspace keep |
| `restore_container(name, preserve_workspace)` | Run from snapshot image |

---

## Supervisor stdio proxy

| Function | Purpose |
| --- | --- |
| `_supervisor_exec_command(...)` | Build `docker exec` argv for supervisor module |
| `start_container_supervisor()` | Popen supervisor process with pipes |
| `healthcheck_container_supervisor(timeout_s)` | Run `--healthcheck`, expect pong line |
| `_supervisor_python_missing(message)` | Detect missing venv/python in stderr |
| `ensure_supervisor_ready(...)` | Start container, run healthcheck, optional rebuild |
| `_read_pipe_chunk(source)` | Non-blocking pipe read helper |
| `_forward_binary_stream(source, sink, close_sink)` | Copy bytes between streams |
| `_read_stdin_to_queue(input_stream, queue, eof)` | Host stdin → queue thread |
| `_write_queue_to_process(queue, process, eof)` | Queue → container supervisor stdin |
| `pipe_to_container_supervisor(...)` | Main [server](server/) loop: ensure container, reconnect on supervisor exit, forward stdio |

---

## Docker exec bash

| Function | Purpose |
| --- | --- |
| `_docker_exec_shell(script, container_cwd, timeout, user)` | Low-level `docker exec` with bash `-lc` |
| `_read_docker_job_file(container_job_dir, stream, ...)` | Read stdout/stderr files from container job dir via exec cat |
| `_refresh_docker_job(job)` | Update job status from container pid/exit files |
| `list_background_jobs()` | List jobs; refresh docker runtime status |
| `foreground_background_job(job_id)` | Incremental output for docker background job |
| `kill_background_job(job_id)` | Kill process in container; mark killed |
| `_exec_bash_docker_background(...)` | Background spool on container disk; host mirrors via JOB_REGISTRY |
| `_exec_bash_docker(...)` | Sync bash: bounded collectors, timeout, optional background routing, legacy path rewrite |

---

## Status

| Function | Purpose |
| --- | --- |
| `get_status()` | Docker daemon, container state, task dir listing, configured limits (no forced start) |

---

## Related

- [_index](_index/)
- [server](server/)
- [supervisor/sandbox/exec](supervisor/sandbox/exec/)
