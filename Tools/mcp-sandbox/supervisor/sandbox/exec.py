# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Native subprocess execution — runs inside the container.

This module has no docker dependencies and can be imported on any platform.
Everything here runs as direct subprocesses inside the already-running sandbox.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
import time
import uuid
from typing import Callable

from sandbox.config import (
    BACKGROUND_TIMEOUT_THRESHOLD,
    COMMAND_USER,
    DEFAULT_TIMEOUT,
    MAX_OUTPUT_CHARS,
)
from sandbox.jobs import BackgroundJob, JOB_REGISTRY
from sandbox.workspace import (
    get_secure_task_path,
    normalize_model_relative_path,
    task_root,
)

logger = __import__("logging").getLogger(__name__)


# ── Shared output helpers ────────────────────────────────────────────

def _truncate(value: str | None) -> tuple[str, bool]:
    """Trim output to MAX_OUTPUT_CHARS, keeping the tail."""
    if value is None:
        return "", False
    if len(value) <= MAX_OUTPUT_CHARS:
        return value, False
    return value[-MAX_OUTPUT_CHARS:], True


def _read_stream_chunks(
    stream,
    sink: list[str],
    callback: Callable[[str], None] | None = None,
) -> None:
    """Read process output in chunks and forward it to an optional callback."""
    while True:
        chunk = stream.read(1024)
        if not chunk:
            break
        sink.append(chunk)
        if callback is not None:
            callback(chunk)


# ── Background job helpers ───────────────────────────────────────────

_LONG_RUNNING_PATTERNS = re.compile(
    r"\b("
    r"apt-get|pip|npm|pnpm|yarn|cargo|pytest|make|cmake|"
    r"docker\s+build|go\s+build|rustc|gcc|g\+\+|webpack|train|epoch"
    r")\b",
    re.IGNORECASE,
)


def _normalize_background_mode(background: str | bool | None) -> str:
    if background is True:
        return "always"
    if background is False or background is None:
        return "auto"
    normalized = str(background).strip().lower()
    if normalized not in {"auto", "always", "never"}:
        raise ValueError("background must be one of: auto, always, never.")
    return normalized


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


def _job_files_result(
    job: BackgroundJob, *, incremental: bool = True
) -> tuple[str, str, bool]:
    stdout = JOB_REGISTRY.read_output(job.job_id, "stdout", incremental=incremental)
    stderr = JOB_REGISTRY.read_output(job.job_id, "stderr", incremental=incremental)
    stdout, trunc_out = _truncate(stdout)
    stderr, trunc_err = _truncate(stderr)
    return stdout, stderr, trunc_out or trunc_err


# ── User / process helpers ───────────────────────────────────────────

def _popen_user_kwargs() -> dict:
    """Return POSIX-only Popen user-switching options for model commands."""
    if os.name != "posix" or not COMMAND_USER or COMMAND_USER == "root":
        return {}
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0:
        return {}
    return {"user": COMMAND_USER}


def _command_user_env() -> dict[str, str]:
    """Return environment overrides for the model command user."""
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


def _kill_process_group(process: subprocess.Popen) -> None:
    """Best-effort kill for the command's process group."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except ProcessLookupError:
            return
        except Exception:
            pass
    process.kill()


# ── Native execution ─────────────────────────────────────────────────

def _exec_bash_native_background(
    command: str,
    cwd: str = ".",
    timeout_s: int = DEFAULT_TIMEOUT,
    stdin: str | None = None,
    on_progress: Callable[[float, str], None] | None = None,
) -> dict:
    """Run a native command as a tracked background-capable job."""
    target_dir = get_secure_task_path(cwd, kind="cwd")
    if not target_dir.exists():
        raise FileNotFoundError(f"cwd not found: {normalize_model_relative_path(cwd)}")
    if not target_dir.is_dir():
        raise NotADirectoryError(
            f"cwd is not a directory: {normalize_model_relative_path(cwd)}"
        )

    start_time = time.time()
    job_id = _new_background_job_id()
    job_dir = task_root() / ".sandbox_jobs" / job_id
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

    job = JOB_REGISTRY.create(
        command=command,
        cwd=normalize_model_relative_path(cwd),
        runtime="native",
        pid=process.pid,
        process=process,
        host_job_dir=job_dir,
        job_id=job_id,
    )

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
    stdout, stderr, truncated = _job_files_result(job, incremental=False)
    if on_progress is not None:
        on_progress(100.0, f"Bash finished in {normalize_model_relative_path(cwd)}")

    # Job completed synchronously — clean up its dir, it won't be polled.
    import shutil
    shutil.rmtree(job_dir, ignore_errors=True)

    return {
        "exit_code": process.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "error": None if process.returncode == 0 else f"Exit code: {process.returncode}",
        "job_id": job.job_id,
        "elapsed_ms": int((time.time() - start_time) * 1000),
        "truncated": truncated,
        "cwd": normalize_model_relative_path(cwd),
    }


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
    """Execute a bash command natively inside the already-running container."""
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

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
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
            break
        if on_progress is not None:
            progress = min(95.0, max(5.0, (elapsed_s / timeout_s) * 90.0))
            on_progress(progress, f"Running bash in {normalize_model_relative_path(cwd)}")
        time.sleep(0.2)

    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)

    stdout_value, trunc_out = _truncate("".join(stdout_chunks))
    stderr_value, trunc_err = _truncate("".join(stderr_chunks))

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
