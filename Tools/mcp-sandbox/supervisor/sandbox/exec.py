# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from sandbox.config import (
    BACKGROUND_TIMEOUT_THRESHOLD,
    COMMAND_USER,
    DEFAULT_TIMEOUT,
    JOB_ROOT,
    MAX_OUTPUT_BYTES,
    OUTPUT_HEAD_RATIO,
)
from sandbox.jobs import BackgroundJob, JOB_REGISTRY
from sandbox.workspace import (
    get_secure_task_path,
    normalize_model_relative_path,
)

logger = __import__("logging").getLogger(__name__)


# Shared output helpers

def _slice_utf8(data: bytes, start: int | None = None, end: int | None = None) -> str:
    return data[start:end].decode("utf-8", errors="ignore")


# Trim output to a configurable head/tail window with an inline marker.
def _truncate(value: str | None) -> tuple[str, bool]:
    if value is None:
        return "", False
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return value, False
    head_ratio = min(0.9, max(0.1, OUTPUT_HEAD_RATIO))
    head_bytes = max(1, int(MAX_OUTPUT_BYTES * head_ratio))
    tail_bytes = max(1, MAX_OUTPUT_BYTES - head_bytes)
    shown_bytes = min(len(encoded), head_bytes + tail_bytes)
    marker = (
        "\n\n"
        f"[output truncated: showed first {head_bytes} bytes and "
        f"last {tail_bytes} bytes of {len(encoded)} bytes]\n\n"
    )
    return (
        _slice_utf8(encoded, 0, head_bytes)
        + marker
        + _slice_utf8(encoded, len(encoded) - tail_bytes, None),
        shown_bytes < len(encoded),
    )


# Collect process output with a fixed head/tail memory budget.
class BoundedOutputCollector:
    def __init__(self) -> None:
        self._buffer = bytearray()
        self._head = bytearray()
        self._tail = bytearray()
        self._total = 0
        head_ratio = min(0.9, max(0.1, OUTPUT_HEAD_RATIO))
        self._head_bytes = max(1, int(MAX_OUTPUT_BYTES * head_ratio))
        self._tail_bytes = max(1, MAX_OUTPUT_BYTES - self._head_bytes)

    def append(self, chunk: str) -> None:
        data = chunk.encode("utf-8", errors="replace")
        if not data:
            return

        if self._buffer is not None:
            self._buffer.extend(data)
            self._total = len(self._buffer)
            if len(self._buffer) <= MAX_OUTPUT_BYTES:
                return
            self._head = self._buffer[: self._head_bytes]
            self._tail = self._buffer[-self._tail_bytes :]
            self._buffer = None
            return

        self._total += len(data)
        self._tail.extend(data)
        if len(self._tail) > self._tail_bytes:
            del self._tail[: len(self._tail) - self._tail_bytes]

    def value(self) -> tuple[str, bool]:
        if self._buffer is not None:
            return self._buffer.decode("utf-8", errors="replace"), False

        marker = (
            "\n\n"
            f"[output truncated: showed first {self._head_bytes} bytes and "
            f"last {self._tail_bytes} bytes of {self._total} bytes]\n\n"
        )
        return (
            self._head.decode("utf-8", errors="replace")
            + marker
            + self._tail.decode("utf-8", errors="replace"),
            True,
        )


# Read process output in chunks and forward each chunk to an optional callback.
def _read_stream_chunks(
    stream,
    sink: BoundedOutputCollector,
    callback: Callable[[str], None] | None = None,
) -> None:
    while True:
        chunk = stream.read(1024)
        if not chunk:
            break
        sink.append(chunk)
        if callback is not None:
            callback(chunk)


# Background job helpers

_LONG_RUNNING_PATTERNS = re.compile(
    r"\b("
    r"apt-get|pip|npm|pnpm|yarn|cargo|pytest|make|cmake|"
    r"docker\s+build|go\s+build|rustc|gcc|g\+\+|webpack|train|epoch"
    r")\b",
    re.IGNORECASE,
)


# Map bool/None background flag to auto | always | never.
def _normalize_background_mode(background: str | bool | None) -> str:
    if background is True:
        return "always"
    if background is False or background is None:
        return "auto"
    normalized = str(background).strip().lower()
    if normalized not in {"auto", "always", "never"}:
        raise ValueError("background must be one of: auto, always, never.")
    return normalized


# Decide whether a command should run as a tracked background job.
def should_use_background(
    command: str, timeout_s: int, background: str | bool | None = "auto"
) -> bool:
    mode = _normalize_background_mode(background)
    if mode == "always":
        return True
    if mode == "never":
        return False
    return timeout_s >= BACKGROUND_TIMEOUT_THRESHOLD or bool(
        _LONG_RUNNING_PATTERNS.search(command)
    )


def _new_background_job_id() -> str:
    return f"bg_{uuid.uuid4().hex[:8]}"


# Ensure JOB_ROOT exists and return its Path.
def job_root() -> Path:
    root = Path(JOB_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


# Bash-shaped dict when foreground wait hits timeout but the job keeps running.
def _background_error_result(
    *,
    job: BackgroundJob,
    stdout: str,
    stderr: str,
    start_time: float,
    timeout_s: int,
    cwd: str,
    truncated: bool = False,
) -> dict:
    return {
        "exit_code": None,
        "stdout": stdout,
        "stderr": stderr,
        "error": f"Process still running in background after {timeout_s} seconds.",
        "error_type": "backgrounded",
        "job_id": job.job_id,
        "elapsed_ms": int((time.time() - start_time) * 1000),
        "truncated": truncated,
        "cwd": normalize_model_relative_path(cwd),
    }


# Read and truncate background job spool files (stdout/stderr).
def _job_files_result(
    job: BackgroundJob, *, incremental: bool = True
) -> tuple[str, str, bool]:
    stdout = JOB_REGISTRY.read_output(job.job_id, "stdout", incremental=incremental)
    stderr = JOB_REGISTRY.read_output(job.job_id, "stderr", incremental=incremental)
    stdout, trunc_out = _truncate(stdout)
    stderr, trunc_err = _truncate(stderr)
    return stdout, stderr, trunc_out or trunc_err


# User / process helpers

# POSIX-only Popen user-switching options when supervisor runs as root.
def _popen_user_kwargs() -> dict:
    if os.name != "posix" or not COMMAND_USER or COMMAND_USER == "root":
        return {}
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0:
        return {}
    return {"user": COMMAND_USER}


# Environment overrides (HOME, USER, SHELL) for the model command user.
def _command_user_env() -> dict[str, str]:
    if os.name != "posix" or not COMMAND_USER or COMMAND_USER == "root":
        return {}
    try:
        import pwd
        user_info = pwd.getpwnam(COMMAND_USER)
    except Exception:
        return {"USER": COMMAND_USER, "LOGNAME": COMMAND_USER}
    return {
        "HOME": user_info.pw_dir,
        "USER": COMMAND_USER,
        "LOGNAME": COMMAND_USER,
        "SHELL": user_info.pw_shell or "/bin/bash",
    }


# Best-effort SIGTERM then SIGKILL for the command's process group.
def _kill_process_group(process: subprocess.Popen) -> None:
    if os.name == "posix":
        try:
            pgid = os.getpgid(process.pid)
        except ProcessLookupError:
            return
        except Exception:
            pgid = process.pid
        try:
            os.killpg(pgid, signal.SIGTERM)
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    return
                time.sleep(0.05)
            os.killpg(pgid, signal.SIGKILL)
            return
        except ProcessLookupError:
            return
        except Exception:
            pass
    process.kill()


# Block until the process exits after a kill (best-effort).
def _wait_after_kill(process: subprocess.Popen, timeout: float = 2.0) -> None:
    try:
        process.wait(timeout=timeout)
    except Exception:
        pass


# Native execution

# Run bash with output spooled to disk; may return early as a background job.
def _exec_bash_native_background(
    command: str,
    cwd: str = ".",
    timeout_s: int = DEFAULT_TIMEOUT,
    stdin: str | None = None,
    on_progress: Callable[[float, str], None] | None = None,
) -> dict:
    target_dir = get_secure_task_path(cwd, kind="cwd")
    if not target_dir.exists():
        raise FileNotFoundError(f"cwd not found: {normalize_model_relative_path(cwd)}")
    if not target_dir.is_dir():
        raise NotADirectoryError(
            f"cwd is not a directory: {normalize_model_relative_path(cwd)}"
        )

    start_time = time.time()
    job_id = _new_background_job_id()
    job_dir = job_root() / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = job_dir / "stdout"
    stderr_path = job_dir / "stderr"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")

    exec_cmd = ["bash", "-lc", command]
    env = os.environ.copy()
    env.update({"PYTHONIOENCODING": "utf-8", "LANG": "C.UTF-8"})
    env.update(_command_user_env())

    try:
        with (
            stdout_path.open("w", encoding="utf-8") as stdout_file,
            stderr_path.open("w", encoding="utf-8") as stderr_file,
        ):
            process = subprocess.Popen(
                exec_cmd,
                cwd=str(target_dir),
                env=env,
                stdin=subprocess.PIPE if stdin is not None else None,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=True,
                **_popen_user_kwargs(),
            )
    except Exception as exc:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": str(exc),
            "elapsed_ms": int((time.time() - start_time) * 1000),
            "truncated": False,
            "cwd": normalize_model_relative_path(cwd),
        }

    if stdin is not None and process.stdin is not None:
        try:
            process.stdin.write(stdin)
        except BrokenPipeError:
            pass
        finally:
            process.stdin.close()

    (job_dir / "pid").write_text(f"{process.pid}\n", encoding="utf-8")
    (job_dir / "pgid").write_text(f"{process.pid}\n", encoding="utf-8")
    (job_dir / "status").write_text("running\n", encoding="utf-8")

    job = JOB_REGISTRY.create(
        command=command,
        cwd=normalize_model_relative_path(cwd),
        runtime="native",
        pid=process.pid,
        process=process,
        host_job_dir=job_dir,
        job_id=job_id,
    )

    # Poll until exit or foreground timeout → backgrounded error result.
    while process.poll() is None:
        elapsed_s = time.time() - start_time
        if elapsed_s >= timeout_s:
            stdout, stderr, truncated = _job_files_result(job, incremental=True)
            return _background_error_result(
                job=job,
                stdout=stdout,
                stderr=stderr,
                start_time=start_time,
                timeout_s=timeout_s,
                cwd=cwd,
                truncated=truncated,
            )
        if on_progress is not None:
            progress = min(95.0, max(5.0, (elapsed_s / timeout_s) * 90.0))
            on_progress(progress, f"Running bash in {normalize_model_relative_path(cwd)}")
        time.sleep(0.2)

    JOB_REGISTRY.mark_done(job.job_id, process.returncode)
    (job_dir / "status").write_text("done\n", encoding="utf-8")
    (job_dir / "exit_code").write_text(f"{process.returncode}\n", encoding="utf-8")
    stdout, stderr, truncated = _job_files_result(job, incremental=False)
    if on_progress is not None:
        on_progress(100.0, f"Bash finished in {normalize_model_relative_path(cwd)}")

    # Job completed synchronously — clean up its dir, it won't be polled.
    JOB_REGISTRY.remove(job.job_id, cleanup=True)

    return {
        "exit_code": process.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "error": None if process.returncode == 0 else f"Exit code: {process.returncode}",
        "elapsed_ms": int((time.time() - start_time) * 1000),
        "truncated": truncated,
        "cwd": normalize_model_relative_path(cwd),
    }


# Execute bash in-process with piped stdout/stderr and optional background routing.
def _exec_bash_native(
    command: str,
    cwd: str = ".",
    timeout_s: int = DEFAULT_TIMEOUT,
    stdin: str | None = None,
    on_stdout: Callable[[str], None] | None = None,
    on_stderr: Callable[[str], None] | None = None,
    on_progress: Callable[[float, str], None] | None = None,
    background: str | bool | None = "never",
) -> dict:
    if timeout_s <= 0:
        raise ValueError("timeout_s must be greater than 0.")

    if should_use_background(command, timeout_s, background):
        return _exec_bash_native_background(
            command=command,
            cwd=cwd,
            timeout_s=timeout_s,
            stdin=stdin,
            on_progress=on_progress,
        )

    target_dir = get_secure_task_path(cwd, kind="cwd")
    if not target_dir.exists():
        raise FileNotFoundError(f"cwd not found: {normalize_model_relative_path(cwd)}")
    if not target_dir.is_dir():
        raise NotADirectoryError(
            f"cwd is not a directory: {normalize_model_relative_path(cwd)}"
        )

    start_time = time.time()
    exec_cmd = ["bash", "-lc", command]
    env = os.environ.copy()
    env.update({"PYTHONIOENCODING": "utf-8", "LANG": "C.UTF-8"})
    env.update(_command_user_env())

    try:
        process = subprocess.Popen(
            exec_cmd,
            cwd=str(target_dir),
            env=env,
            stdin=subprocess.PIPE if stdin is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
            **_popen_user_kwargs(),
        )
    except Exception as exc:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": str(exc),
            "elapsed_ms": int((time.time() - start_time) * 1000),
            "truncated": False,
            "cwd": normalize_model_relative_path(cwd),
        }

    stdout_chunks = BoundedOutputCollector()
    stderr_chunks = BoundedOutputCollector()
    stdout_thread = threading.Thread(
        target=_read_stream_chunks,
        args=(process.stdout, stdout_chunks, on_stdout),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_read_stream_chunks,
        args=(process.stderr, stderr_chunks, on_stderr),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    # Wait for process exit, progress callbacks, or timeout → kill group.
    if stdin is not None and process.stdin is not None:
        try:
            process.stdin.write(stdin)
        except BrokenPipeError:
            pass
        finally:
            process.stdin.close()

    timed_out = False
    while process.poll() is None:
        elapsed_s = time.time() - start_time
        if elapsed_s >= timeout_s:
            timed_out = True
            _kill_process_group(process)
            _wait_after_kill(process)
            break
        if on_progress is not None:
            progress = min(95.0, max(5.0, (elapsed_s / timeout_s) * 90.0))
            on_progress(progress, f"Running bash in {normalize_model_relative_path(cwd)}")
        time.sleep(0.2)

    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)

    stdout_value, trunc_out = stdout_chunks.value()
    stderr_value, trunc_err = stderr_chunks.value()

    if timed_out:
        return {
            "exit_code": None,
            "stdout": stdout_value,
            "stderr": stderr_value,
            "error": f"Execution timed out after {timeout_s} seconds. Process group killed.",
            "elapsed_ms": int((time.time() - start_time) * 1000),
            "truncated": trunc_out or trunc_err,
            "cwd": normalize_model_relative_path(cwd),
        }

    if on_progress is not None:
        on_progress(100.0, f"Bash finished in {normalize_model_relative_path(cwd)}")

    return {
        "exit_code": process.returncode,
        "stdout": stdout_value,
        "stderr": stderr_value,
        "error": None if process.returncode == 0 else f"Exit code: {process.returncode}",
        "elapsed_ms": int((time.time() - start_time) * 1000),
        "truncated": trunc_out or trunc_err,
        "cwd": normalize_model_relative_path(cwd),
    }
