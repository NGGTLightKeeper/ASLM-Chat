# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import contextlib
import codecs
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from queue import Empty, Queue
from typing import Any, Iterator

from sandbox.config import (
    COMMAND_USER,
    DEFAULT_TASK_DIR,
    MAX_OUTPUT_BYTES,
    MODEL_WORKSPACE_CONTAINER,
    SANDBOX_IMAGE,
    STORAGE_LIMIT,
)
from sandbox.docker_host import (
    _build_run_command,
    _ensure_docker_running,
    _ensure_image,
    _run_command,
    _storage_limit_unsupported,
)
from sandbox.responses import error_response, success_response


TEMPORAL_CONTAINER_PREFIX = "aslm-deep-research-"
TEMPORAL_WORKSPACE_PREFIX = "aslm-deep-research-"
_SAFE_CONTAINER_PATTERN = re.compile(r"^aslm-deep-research-[a-f0-9]{12,32}$")


def _safe_temporal_workspace(path: str | Path) -> Path:
    candidate = Path(path).resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    try:
        relative = candidate.relative_to(temp_root)
    except ValueError as exc:
        raise ValueError("Temporal sandbox workspace must be under the system temp directory.") from exc
    if len(relative.parts) != 1 or not candidate.name.startswith(TEMPORAL_WORKSPACE_PREFIX):
        raise ValueError("Invalid temporal sandbox workspace name.")
    return candidate


def _safe_temporal_container_name(value: Any) -> str:
    name = str(value or "").strip()
    if not _SAFE_CONTAINER_PATTERN.fullmatch(name):
        raise ValueError("Invalid temporal sandbox container name.")
    return name


def _container_running(name: str) -> bool:
    try:
        result = _run_command(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def _container_exists(name: str) -> bool:
    try:
        result = _run_command(["docker", "inspect", name], timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _remove_container(name: str) -> None:
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        _run_command(["docker", "rm", "-f", name], timeout=30)


def _start_container(name: str, workspace: Path) -> tuple[bool, str]:
    docker_ok, docker_message = _ensure_docker_running()
    if not docker_ok:
        return False, docker_message
    image_ok, image_message = _ensure_image()
    if not image_ok:
        return False, image_message

    workspace.mkdir(parents=True, exist_ok=True)
    _remove_container(name)
    include_storage_limit = bool(STORAGE_LIMIT)
    command = _build_run_command(
        SANDBOX_IMAGE,
        include_storage_limit=include_storage_limit,
        container_name=name,
        task_host_path=str(workspace),
        restart_policy=None,
        auto_remove=True,
    )
    result = _run_command(command, timeout=60)
    if result.returncode != 0 and include_storage_limit and _storage_limit_unsupported(result.stderr):
        command = _build_run_command(
            SANDBOX_IMAGE,
            include_storage_limit=False,
            container_name=name,
            task_host_path=str(workspace),
            restart_policy=None,
            auto_remove=True,
        )
        result = _run_command(command, timeout=60)
    if result.returncode != 0:
        return False, result.stderr.strip() or "Could not start temporal sandbox container."

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if _container_running(name):
            return True, "Temporal sandbox container is running."
        time.sleep(0.2)
    _remove_container(name)
    return False, "Temporal sandbox container did not reach running state."


def _ensure_container(name: str, workspace: Path) -> tuple[bool, str]:
    if _container_running(name):
        return True, "Temporal sandbox container is running."
    return _start_container(name, workspace)


def _normalize_cwd(value: Any) -> str:
    raw = str(value or ".").strip().replace("\\", "/") or "."
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Temporal sandbox cwd must be relative to the workspace.")
    normalized = path.as_posix()
    return "." if normalized in ("", ".") else normalized


def _truncate_output(value: str) -> tuple[str, bool]:
    encoded = str(value or "").encode("utf-8", errors="replace")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return encoded.decode("utf-8", errors="replace"), False
    head_size = max(1, MAX_OUTPUT_BYTES // 2)
    tail_size = max(1, MAX_OUTPUT_BYTES - head_size)
    head = encoded[:head_size].decode("utf-8", errors="replace")
    tail = encoded[-tail_size:].decode("utf-8", errors="replace")
    return f"{head}\n\n[output truncated]\n\n{tail}", True


def _emit_event(context: dict[str, Any], event_type: str, data: dict[str, Any]) -> None:
    callback = context.get("event_callback")
    if not callable(callback):
        return
    try:
        callback(
            {
                "type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data,
            }
        )
    except Exception:
        pass


def _run_process_streaming(
    command: list[str],
    *,
    stdin_value: Any,
    timeout_s: int,
    context: dict[str, Any],
) -> tuple[int | None, str, str, bool]:
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdin is not None:
        try:
            if stdin_value is not None:
                with contextlib.suppress(BrokenPipeError):
                    process.stdin.write(str(stdin_value).encode("utf-8"))
                    process.stdin.flush()
        finally:
            process.stdin.close()

    output_queue: Queue[tuple[str, str | None]] = Queue()
    fragments: dict[str, list[str]] = {"stdout": [], "stderr": []}

    def read_stream(stream_name: str, stream: Any) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while True:
                read = getattr(stream, "read1", stream.read)
                chunk = read(4096)
                if not chunk:
                    break
                text = decoder.decode(chunk)
                if text:
                    output_queue.put((stream_name, text))
            tail = decoder.decode(b"", final=True)
            if tail:
                output_queue.put((stream_name, tail))
        finally:
            output_queue.put((stream_name, None))

    readers = [
        threading.Thread(
            target=read_stream,
            args=(stream_name, stream),
            name=f"aslm-temporal-bash-{stream_name}",
            daemon=True,
        )
        for stream_name, stream in (("stdout", process.stdout), ("stderr", process.stderr))
        if stream is not None
    ]
    for reader in readers:
        reader.start()

    deadline = time.monotonic() + timeout_s
    completed_streams = 0
    timed_out = False
    while completed_streams < len(readers):
        remaining = deadline - time.monotonic()
        if remaining <= 0 and process.poll() is None:
            timed_out = True
            process.kill()
        try:
            stream_name, content = output_queue.get(timeout=max(0.01, min(0.1, remaining)))
        except Empty:
            if process.poll() is not None and all(not reader.is_alive() for reader in readers):
                break
            continue
        if content is None:
            completed_streams += 1
            continue
        fragments[stream_name].append(content)
        _emit_event(context, "bash_output", {"stream": stream_name, "content": content})

    if timed_out and process.poll() is None:
        process.kill()
    try:
        return_code = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        return_code = process.wait(timeout=5)
    for reader in readers:
        reader.join(timeout=1)
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            with contextlib.suppress(OSError):
                stream.close()

    while True:
        try:
            stream_name, content = output_queue.get_nowait()
        except Empty:
            break
        if content:
            fragments[stream_name].append(content)
            _emit_event(context, "bash_output", {"stream": stream_name, "content": content})
    return return_code, "".join(fragments["stdout"]), "".join(fragments["stderr"]), timed_out


def temporal_sandbox_spec() -> dict[str, str]:
    token = uuid.uuid4().hex[:16]
    workspace = Path(tempfile.mkdtemp(prefix=TEMPORAL_WORKSPACE_PREFIX)).resolve()
    return {
        "container_name": f"{TEMPORAL_CONTAINER_PREFIX}{token}",
        "host_workspace": str(workspace),
    }


def cleanup_temporal_sandbox(spec: dict[str, Any]) -> None:
    name = _safe_temporal_container_name(spec.get("container_name"))
    workspace = _safe_temporal_workspace(str(spec.get("host_workspace") or ""))
    for attempt in range(3):
        _remove_container(name)
        if not _container_exists(name):
            break
        time.sleep(0.1 * (attempt + 1))
    if _container_exists(name):
        raise RuntimeError(f"Temporal sandbox container cleanup failed: {name}")

    for attempt in range(3):
        if not workspace.exists():
            break
        try:
            shutil.rmtree(workspace)
        except OSError:
            if attempt == 2:
                raise
            time.sleep(0.1 * (attempt + 1))
    if workspace.exists():
        raise RuntimeError(f"Temporal sandbox workspace cleanup failed: {workspace}")


@contextmanager
def temporal_sandbox() -> Iterator[dict[str, str]]:
    spec = temporal_sandbox_spec()
    try:
        yield spec
    finally:
        cleanup_temporal_sandbox(spec)


def run_temporal_bash(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    spec = context.get("temporal_sandbox") if isinstance(context.get("temporal_sandbox"), dict) else {}
    try:
        name = _safe_temporal_container_name(spec.get("container_name"))
        workspace = _safe_temporal_workspace(str(spec.get("host_workspace") or ""))
        cwd = _normalize_cwd(arguments.get("cwd"))
        command = str(arguments.get("command") or "").strip()
        timeout_s = min(3600, max(1, int(arguments.get("timeout_s") or 60)))
        if not command:
            raise ValueError("bash command must not be empty.")
    except (TypeError, ValueError) as exc:
        return error_response("bash", "invalid_arguments", str(exc))

    _emit_event(
        context,
        "sandbox_container_starting",
        {"container_name": name, "host_workspace": str(workspace)},
    )
    container_ok, container_message = _ensure_container(name, workspace)
    if not container_ok:
        _emit_event(
            context,
            "sandbox_container_failed",
            {"container_name": name, "message": container_message},
        )
        return error_response("bash", "container_unavailable", container_message)
    _emit_event(
        context,
        "sandbox_container_ready",
        {"container_name": name, "message": container_message},
    )

    container_cwd = MODEL_WORKSPACE_CONTAINER
    if cwd != ".":
        container_cwd = f"{MODEL_WORKSPACE_CONTAINER}/{cwd}"
    exec_command = ["docker", "exec", "-i"]
    if COMMAND_USER and COMMAND_USER != "root":
        exec_command.extend(["-u", COMMAND_USER])
    exec_command.extend(
        [
            "-w", container_cwd,
            "-e", "PYTHONIOENCODING=utf-8",
            "-e", "LANG=C.UTF-8",
            "-e", f"SANDBOX_DEFAULT_TASK_DIR={DEFAULT_TASK_DIR}",
            name, "bash", "-lc", command,
        ]
    )

    started = time.monotonic()
    _emit_event(
        context,
        "bash_started",
        {"command": command, "cwd": cwd, "timeout_s": timeout_s},
    )
    try:
        if callable(context.get("event_callback")):
            return_code, raw_stdout, raw_stderr, timed_out = _run_process_streaming(
                exec_command,
                stdin_value=arguments.get("stdin"),
                timeout_s=timeout_s,
                context=context,
            )
            if timed_out:
                _remove_container(name)
                stdout, trunc_out = _truncate_output(raw_stdout)
                stderr, trunc_err = _truncate_output(raw_stderr)
                elapsed_ms = int((time.monotonic() - started) * 1000)
                _emit_event(
                    context,
                    "bash_timed_out",
                    {
                        "command": command,
                        "cwd": cwd,
                        "timeout_s": timeout_s,
                        "elapsed_ms": elapsed_ms,
                        "container_removed": True,
                    },
                )
                return error_response(
                    "bash",
                    "timeout",
                    f"Execution timed out after {timeout_s} seconds; the temporal container was removed.",
                    result={
                        "command": command,
                        "cwd": cwd,
                        "exit_code": None,
                        "stdout": stdout,
                        "stderr": stderr,
                        "elapsed_ms": elapsed_ms,
                    },
                    truncated=trunc_out or trunc_err,
                )
            result = subprocess.CompletedProcess(
                args=exec_command,
                returncode=int(return_code or 0),
                stdout=raw_stdout,
                stderr=raw_stderr,
            )
        else:
            result = subprocess.run(
                exec_command,
                input=arguments.get("stdin"),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
            )
    except subprocess.TimeoutExpired as exc:
        _remove_container(name)
        stdout, trunc_out = _truncate_output(str(exc.stdout or ""))
        stderr, trunc_err = _truncate_output(str(exc.stderr or ""))
        elapsed_ms = int((time.monotonic() - started) * 1000)
        _emit_event(
            context,
            "bash_timed_out",
            {
                "command": command,
                "cwd": cwd,
                "timeout_s": timeout_s,
                "elapsed_ms": elapsed_ms,
                "container_removed": True,
            },
        )
        return error_response(
            "bash",
            "timeout",
            f"Execution timed out after {timeout_s} seconds; the temporal container was removed.",
            result={
                "command": command,
                "cwd": cwd,
                "exit_code": None,
                "stdout": stdout,
                "stderr": stderr,
                "elapsed_ms": elapsed_ms,
            },
            truncated=trunc_out or trunc_err,
        )
    except OSError as exc:
        _emit_event(
            context,
            "bash_failed",
            {"command": command, "cwd": cwd, "message": str(exc)},
        )
        return error_response("bash", "execution_failed", str(exc))

    stdout, trunc_out = _truncate_output(result.stdout)
    stderr, trunc_err = _truncate_output(result.stderr)
    payload = {
        "command": command,
        "cwd": cwd,
        "exit_code": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }
    warnings = ["Command output was truncated."] if trunc_out or trunc_err else []
    _emit_event(
        context,
        "bash_completed",
        {
            "command": command,
            "cwd": cwd,
            "exit_code": result.returncode,
            "elapsed_ms": payload["elapsed_ms"],
            "stdout_chars": len(result.stdout),
            "stderr_chars": len(result.stderr),
            "truncated": bool(warnings),
        },
    )
    if result.returncode == 0:
        return success_response("bash", payload, warnings=warnings, truncated=bool(warnings))
    return error_response(
        "bash",
        "process_error",
        f"Exit code: {result.returncode}",
        result=payload,
        warnings=warnings,
        truncated=bool(warnings),
    )
