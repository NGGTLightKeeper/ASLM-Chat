# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Docker lifecycle, supervisor pipe, and docker-exec backend — host-side only.

This module must only be imported on the host. Inside the container use exec.py.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import Callable

from sandbox.config import (
    BACKGROUND_TIMEOUT_THRESHOLD,
    COMMAND_USER,
    CONFIG_FILE_PATH,
    CONTAINER_NAME,
    CONTAINER_WORKSPACE,
    CPU_LIMIT,
    DEFAULT_TASK_DIR,
    DEFAULT_TIMEOUT,
    DEV_BIND,
    DOCKER_START_TIMEOUT_SECONDS,
    HOST_WORKSPACE,
    MAX_CAT_FILE_BYTES,
    MAX_CAT_LINE_THRESHOLD,
    MAX_FIND_RESULTS,
    MAX_FILE_MAP_SYMBOLS,
    MAX_GREP_RESULTS,
    MAX_LS_ENTRIES,
    MAX_OUTPUT_BYTES,
    OUTPUT_HEAD_RATIO,
    MAX_READ_BYTES,
    MEMORY_LIMIT,
    MEMORY_SWAP_LIMIT,
    MODEL_WORKSPACE_CONTAINER,
    NETWORK_LIMIT_MBIT,
    PIDS_LIMIT,
    SANDBOX_IMAGE,
    SANDBOX_IMAGE_SOURCE,
    SNAPSHOT_IMAGE_PREFIX,
    STORAGE_LIMIT,
    SUPERVISOR_SRC,
    SUPERVISOR_SRC_HOST,
    SUPERVISOR_VENV,
    SUPERVISOR_VENV_HOST,
    THREAD_LIMIT,
    WORKSPACE_CLEANUP_ENABLED,
    WORKSPACE_CLEANUP_IDLE_SECONDS,
    WORKSPACE_CLEANUP_INTERVAL_SECONDS,
    WORKSPACE_CLEANUP_RECYCLE_SECONDS,
    WINDOWS_DOCKER_DESKTOP_PATHS,
)
from sandbox.exec import (
    BoundedOutputCollector,
    _background_error_result,
    _new_background_job_id,
    _read_stream_chunks,
    _truncate,
)
from sandbox.jobs import BackgroundJob, JOB_REGISTRY
from sandbox.workspace import (
    get_secure_task_path,
    normalize_model_relative_path,
    task_root,
)

logger = logging.getLogger(__name__)

REQUIRED_IMAGE_LABEL = "org.aslm.sandbox.supervisor-runtime"
REQUIRED_IMAGE_LABEL_VALUE = "container-v2"
SUPERVISOR_PONG = "sandbox-supervisor-pong-v2"
LEGACY_UPLOAD_MODEL_ROOT = "/mnt/data/User"
UPLOAD_MODEL_ROOT = f"{MODEL_WORKSPACE_CONTAINER.rstrip('/')}/User"
DEFAULT_DOCKER_JOB_ROOT = "/workspace/.sandbox_jobs"


def _rewrite_legacy_upload_paths(command: str) -> str:
    """Keep old model-facing upload paths usable in plain bash commands."""

    return str(command or "").replace(LEGACY_UPLOAD_MODEL_ROOT, UPLOAD_MODEL_ROOT)


def _resolve_docker_job_root() -> str:
    """Pick a container-writable root for background spool files."""
    configured = (
        os.getenv("SANDBOX_CONTAINER_JOB_ROOT", "").strip()
        or os.getenv("SANDBOX_JOB_ROOT", "").strip()
    )
    if configured.startswith("/"):
        return configured.rstrip("/") or "/"
    return DEFAULT_DOCKER_JOB_ROOT


def _docker_job_root_candidates() -> list[str]:
    """Return ordered job-root candidates for docker background jobs."""
    configured = _resolve_docker_job_root()
    candidates = [
        configured,
        "/workspace/.sandbox_jobs",
        "/tmp/mcp-sandbox-jobs",
        "/dev/shm/mcp-sandbox-jobs",
        "$HOME/.sandbox_jobs",
    ]
    unique: list[str] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


# ── Subprocess helpers ───────────────────────────────────────────────

def _run_command(
    args: list[str],
    timeout: int = 30,
    check: bool = False,
    input_text: str | None = None,
):
    """Run a subprocess command with UTF-8 text handling."""
    return subprocess.run(
        args,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=check,
    )


# ── Docker availability ──────────────────────────────────────────────

def _docker_cli_available() -> bool:
    """Return True when the docker CLI is installed."""
    try:
        result = _run_command(["docker", "--version"], timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def _docker_info(timeout: int = 5):
    """Query docker daemon info."""
    return _run_command(["docker", "info", "--format", "{{json .}}"], timeout=timeout)


def _auto_start_docker_enabled() -> bool:
    """Return whether host tools may launch Docker Desktop automatically."""

    value = os.environ.get("SANDBOX_AUTO_START_DOCKER", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _ensure_docker_running() -> tuple[bool, str]:
    """Ensure the Docker daemon is available."""
    if not _docker_cli_available():
        return False, "Docker CLI not found. Install Docker Desktop first."

    try:
        info_result = _docker_info(timeout=5)
        if info_result.returncode == 0:
            return True, "Docker daemon is running."
    except Exception:
        pass

    if os.name != "nt":
        return False, "Docker daemon is not running. Start Docker and try again."

    if not _auto_start_docker_enabled():
        return (
            False,
            "Docker daemon is not running. Start Docker Desktop manually to use sandbox tools, "
            "or set SANDBOX_AUTO_START_DOCKER=1 to allow automatic launch.",
        )

    launched = False
    for path in WINDOWS_DOCKER_DESKTOP_PATHS:
        if not os.path.isfile(path):
            continue
        subprocess.Popen(
            [path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x00000008,
        )
        launched = True
        break

    if not launched:
        return False, "Docker Desktop not found. Install or start it manually."

    deadline = time.time() + DOCKER_START_TIMEOUT_SECONDS
    while time.time() < deadline:
        time.sleep(2)
        try:
            check_result = _docker_info(timeout=5)
            if check_result.returncode == 0:
                return True, "Docker Desktop started successfully."
        except Exception:
            continue

    return (
        False,
        "Docker Desktop launched but daemon did not respond in "
        f"{DOCKER_START_TIMEOUT_SECONDS}s.",
    )


# ── Container existence checks ───────────────────────────────────────

def _container_exists() -> bool:
    result = _run_command(
        ["docker", "ps", "-aq", "-f", f"name=^{CONTAINER_NAME}$"], timeout=10
    )
    return bool(result.stdout.strip())


def _container_is_running() -> bool:
    result = _run_command(
        ["docker", "ps", "-q", "-f", f"name=^{CONTAINER_NAME}$"], timeout=10
    )
    return bool(result.stdout.strip())


# ── Image preparation ────────────────────────────────────────────────

def _image_has_required_runtime(inspect_stdout: str) -> bool:
    try:
        image_info = json.loads(inspect_stdout)
    except json.JSONDecodeError:
        return False
    if not image_info:
        return False
    labels = image_info[0].get("Config", {}).get("Labels") or {}
    return labels.get(REQUIRED_IMAGE_LABEL) == REQUIRED_IMAGE_LABEL_VALUE


def _ensure_image(force_rebuild: bool = False) -> tuple[bool, str]:
    """Ensure the sandbox image exists locally by delegating to setup-sandbox.py."""
    inspect_result = _run_command(
        ["docker", "image", "inspect", SANDBOX_IMAGE], timeout=20
    )
    if inspect_result.returncode == 0 and not force_rebuild:
        if _image_has_required_runtime(inspect_result.stdout):
            return True, "Image already exists locally."

    setup_script = Path(__file__).resolve().parents[2] / "setup-sandbox.py"
    cmd = [sys.executable, str(setup_script)]
    if force_rebuild:
        cmd.append("--force")
    result = subprocess.run(cmd, timeout=1900)
    if result.returncode == 0:
        return True, f"Image '{SANDBOX_IMAGE}' is ready."
    return False, (
        f"Image setup failed (exit {result.returncode}). "
        "Run setup-sandbox.py manually for details."
    )


# ── Container run command ────────────────────────────────────────────

def _linux_venv_bind_source() -> str | None:
    if not SUPERVISOR_VENV_HOST:
        return None
    venv_path = Path(SUPERVISOR_VENV_HOST).expanduser()
    bin_python = venv_path / "bin" / "python"
    windows_python = venv_path / "Scripts" / "python.exe"
    pyvenv_cfg = venv_path / "pyvenv.cfg"
    if windows_python.exists() or not bin_python.exists() or not pyvenv_cfg.exists():
        raise ValueError(
            "SANDBOX_SUPERVISOR_VENV_HOST must point to a Linux venv "
            "with bin/python and pyvenv.cfg, not a Windows venv."
        )
    return str(venv_path)


_CONFIG_TEMPLATE = """\
# sandbox.env - generated automatically on first launch.
# Uncomment and edit any line to override the default without rebuilding the image.
# Changes take effect the next time the container is (re)started.

# === Container identity ===
#SANDBOX_CONTAINER_NAME=mcp-sandbox
#SANDBOX_IMAGE=dima1312313/mcp-sandbox:latest
#SANDBOX_IMAGE_SOURCE=registry

# === Resource limits (applied at docker run) ===
#SANDBOX_CPU_LIMIT=4
#SANDBOX_MEMORY_LIMIT=3g
#SANDBOX_MEMORY_SWAP_LIMIT=4g
#SANDBOX_PIDS_LIMIT=256
#SANDBOX_STORAGE_LIMIT=12G
#SANDBOX_NETWORK_LIMIT_MBIT=100

# === Execution limits (inside container) ===
#SANDBOX_DEFAULT_TIMEOUT=60
#SANDBOX_MAX_OUTPUT_BYTES=60000
#SANDBOX_OUTPUT_HEAD_RATIO=0.5
#SANDBOX_MAX_READ_BYTES=200000
#SANDBOX_MAX_CAT_FILE_BYTES=30720
#SANDBOX_MAX_CAT_LINE_THRESHOLD=300
#SANDBOX_MAX_IMAGE_PREVIEW_BYTES=2000000
#SANDBOX_MAX_LS_ENTRIES=500
#SANDBOX_MAX_FIND_RESULTS=200
#SANDBOX_MAX_GREP_RESULTS=200
#SANDBOX_BACKGROUND_TIMEOUT_THRESHOLD=10

# === Thread limits ===
#SANDBOX_THREAD_LIMIT=4

# === Workspace ===
#SANDBOX_DEFAULT_TASK_DIR=_sandbox
#SANDBOX_WORKSPACE_CLEANUP_ENABLED=1
#SANDBOX_WORKSPACE_CLEANUP_IDLE_SECONDS=5400
#SANDBOX_WORKSPACE_CLEANUP_RECYCLE_SECONDS=10800
#SANDBOX_WORKSPACE_CLEANUP_INTERVAL_SECONDS=5

#SANDBOX_MAX_FILE_MAP_SYMBOLS=50

# === Docker startup ===
#SANDBOX_DOCKER_START_TIMEOUT_SECONDS=60
"""


def _ensure_sandbox_config(config_path: str = CONFIG_FILE_PATH) -> None:
    """Create sandbox.env with commented-out defaults if it does not exist yet."""
    path = Path(config_path)
    if path.exists():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_CONFIG_TEMPLATE, encoding="utf-8")
        logger.info("Created sandbox config: %s", config_path)
    except OSError as exc:
        logger.warning("Could not create sandbox config %s: %s", config_path, exc)


def _build_run_command(
    image_name: str,
    include_storage_limit: bool = True,
) -> list[str]:
    """Build the docker run command for the sandbox container."""
    command = [
        "docker", "run", "-d",
        "--name", CONTAINER_NAME,
        "--restart", "unless-stopped",
        "--cpus", CPU_LIMIT,
        "--memory", MEMORY_LIMIT,
        "--memory-swap", MEMORY_SWAP_LIMIT,
        "--pids-limit", PIDS_LIMIT,
        "--no-healthcheck",
    ]
    # Do not add --security-opt no-new-privileges here unless the sudo model
    # is redesigned. The sandbox_user intentionally has passwordless sudo for
    # package-manager compatibility, and no-new-privileges would break sudo.

    if NETWORK_LIMIT_MBIT > 0:
        command.extend(["--cap-add", "NET_ADMIN"])

    if include_storage_limit and STORAGE_LIMIT:
        command.extend(["--storage-opt", f"size={STORAGE_LIMIT}"])

    task_host_path = os.path.join(HOST_WORKSPACE, DEFAULT_TASK_DIR)
    os.makedirs(task_host_path, exist_ok=True)
    supervisor_src_host = SUPERVISOR_SRC_HOST
    supervisor_venv_host = _linux_venv_bind_source()

    # Internal container constants — always set explicitly.
    command.extend([
        "-v", f"{task_host_path}:{MODEL_WORKSPACE_CONTAINER}",
        "-w", MODEL_WORKSPACE_CONTAINER,
        # Runtime identity — container-side constants.
        "-e", "SANDBOX_IN_CONTAINER=1",
        "-e", f"SANDBOX_COMMAND_USER={COMMAND_USER}",
        "-e", f"SANDBOX_HOST_WORKSPACE={CONTAINER_WORKSPACE}",
        "-e", f"SANDBOX_DEFAULT_TASK_DIR={DEFAULT_TASK_DIR}",
        "-e", f"SANDBOX_SUPERVISOR_SRC={SUPERVISOR_SRC}",
        "-e", f"SANDBOX_SUPERVISOR_VENV={SUPERVISOR_VENV}",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        # Execution limits — user-configurable via sandbox.env, passed explicitly
        # so that host-only vars (image name, container name, Windows paths, etc.)
        # never leak into the container environment.
        "-e", f"SANDBOX_DEFAULT_TIMEOUT={DEFAULT_TIMEOUT}",
        "-e", f"SANDBOX_MAX_OUTPUT_BYTES={MAX_OUTPUT_BYTES}",
        "-e", f"SANDBOX_OUTPUT_HEAD_RATIO={OUTPUT_HEAD_RATIO}",
        "-e", f"SANDBOX_MAX_READ_BYTES={MAX_READ_BYTES}",
        "-e", f"SANDBOX_MAX_CAT_FILE_BYTES={MAX_CAT_FILE_BYTES}",
        "-e", f"SANDBOX_MAX_CAT_LINE_THRESHOLD={MAX_CAT_LINE_THRESHOLD}",
        "-e", f"SANDBOX_MAX_LS_ENTRIES={MAX_LS_ENTRIES}",
        "-e", f"SANDBOX_MAX_FIND_RESULTS={MAX_FIND_RESULTS}",
        "-e", f"SANDBOX_MAX_GREP_RESULTS={MAX_GREP_RESULTS}",
        "-e", f"SANDBOX_MAX_FILE_MAP_SYMBOLS={MAX_FILE_MAP_SYMBOLS}",
        "-e", f"SANDBOX_BACKGROUND_TIMEOUT_THRESHOLD={BACKGROUND_TIMEOUT_THRESHOLD}",
        "-e", f"SANDBOX_WORKSPACE_CLEANUP_ENABLED={int(WORKSPACE_CLEANUP_ENABLED)}",
        "-e", f"SANDBOX_WORKSPACE_CLEANUP_IDLE_SECONDS={WORKSPACE_CLEANUP_IDLE_SECONDS}",
        "-e", f"SANDBOX_WORKSPACE_CLEANUP_RECYCLE_SECONDS={WORKSPACE_CLEANUP_RECYCLE_SECONDS}",
        "-e", f"SANDBOX_WORKSPACE_CLEANUP_INTERVAL_SECONDS={WORKSPACE_CLEANUP_INTERVAL_SECONDS}",
        "-e", f"SANDBOX_NETWORK_LIMIT_MBIT={NETWORK_LIMIT_MBIT}",
        # Thread limits — propagated to ML libraries too.
        "-e", f"SANDBOX_THREAD_LIMIT={THREAD_LIMIT}",
        "-e", f"OMP_NUM_THREADS={THREAD_LIMIT}",
        "-e", f"OPENBLAS_NUM_THREADS={THREAD_LIMIT}",
        "-e", f"MKL_NUM_THREADS={THREAD_LIMIT}",
        "-e", f"NUMEXPR_NUM_THREADS={THREAD_LIMIT}",
        "-e", f"VECLIB_MAXIMUM_THREADS={THREAD_LIMIT}",
    ])

    if DEV_BIND and supervisor_src_host and os.path.isdir(supervisor_src_host):
        command.extend(["-v", f"{supervisor_src_host}:{SUPERVISOR_SRC}:ro"])

    if DEV_BIND and supervisor_venv_host is not None:
        command.extend(["-v", f"{supervisor_venv_host}:{SUPERVISOR_VENV}:ro"])

    command.append(image_name)
    return command


# ── Container lifecycle ──────────────────────────────────────────────

_container_lock = threading.Lock()


def _ensure_container_running(
    image_name: str = SANDBOX_IMAGE,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> tuple[bool, str]:
    """Ensure the sandbox container is running — idempotent with retry."""
    _ensure_sandbox_config()
    docker_ok, msg = _ensure_docker_running()
    if not docker_ok:
        return False, msg
    with _container_lock:
        return _ensure_container_locked(image_name, max_retries, retry_delay)


def _ensure_container_locked(
    image_name: str,
    max_retries: int,
    retry_delay: float,
) -> tuple[bool, str]:
    last_error = ""
    for attempt in range(max_retries):
        if attempt > 0:
            time.sleep(retry_delay)
            logger.info("Retry %d/%d for container setup", attempt + 1, max_retries)

        state = _inspect_container()

        if state is None:
            ok, msg = _create_container(image_name)
            if not ok:
                if "already in use" in msg.lower():
                    logger.debug("Name conflict on create, will retry")
                last_error = msg
                continue
            running, run_msg = _wait_for_container_running()
            if running:
                return True, msg
            _force_remove()
            last_error = run_msg
            continue

        if state["running"] and state["volume_ok"]:
            return True, "Container is running."

        if not state["volume_ok"]:
            ok, msg = _force_remove()
            if not ok:
                last_error = f"Failed to remove mismatched container: {msg}"
                continue
            ok, msg = _create_container(image_name)
            if not ok:
                last_error = msg
                continue
            running, run_msg = _wait_for_container_running()
            if running:
                return True, msg
            _force_remove()
            last_error = run_msg
            continue

        if state["exists"] and not state["running"]:
            ok, msg = _start_existing()
            if ok:
                return True, msg
            logger.debug("Start failed (%s), removing and recreating", msg)
            _force_remove()
            ok, msg = _create_container(image_name)
            if not ok:
                last_error = msg
                continue
            running, run_msg = _wait_for_container_running()
            if running:
                return True, msg
            _force_remove()
            last_error = run_msg
            continue

    return False, f"Failed after {max_retries} attempts. Last error: {last_error}"


def _inspect_container() -> dict | None:
    result = _run_command(["docker", "inspect", CONTAINER_NAME], timeout=10)
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
        if not data:
            return None
        info = data[0]
        state_dict = info.get("State", {})
        running = state_dict.get("Running", False)
        status = state_dict.get("Status", "unknown")
        mounts = " ".join(m.get("Source", "") for m in info.get("Mounts", []))
        expected_mount = os.path.normcase(
            os.path.normpath(os.path.join(HOST_WORKSPACE, DEFAULT_TASK_DIR))
        )
        actual_mount = os.path.normcase(os.path.normpath(mounts))
        return {
            "exists": True,
            "running": running,
            "status": status,
            "volume_ok": expected_mount in actual_mount.split(),
        }
    except Exception:
        return None


def _force_remove() -> tuple[bool, str]:
    result = _run_command(["docker", "rm", "-f", CONTAINER_NAME], timeout=30)
    if result.returncode == 0:
        return True, "Removed."
    if "no such container" in result.stderr.lower():
        return True, "Already gone."
    return False, result.stderr.strip()


def _start_existing() -> tuple[bool, str]:
    result = _run_command(["docker", "start", CONTAINER_NAME], timeout=30)
    if result.returncode == 0:
        time.sleep(0.5)
        state = _inspect_container()
        if state and state["running"]:
            return True, "Started."
        return False, "Started but not running."
    return False, result.stderr.strip()


def _storage_limit_unsupported(stderr_text: str) -> bool:
    lowered = stderr_text.lower()
    return any(
        indicator in lowered
        for indicator in ["storage-opt", "unknown flag", "quota", "overlay2", "xfs",
                          "not supported", "invalid argument"]
    )


def _create_container(image_name: str) -> tuple[bool, str]:
    build_ok, build_msg = _ensure_image()
    if not build_ok:
        return False, build_msg

    if STORAGE_LIMIT:
        try:
            cmd = _build_run_command(image_name, include_storage_limit=True)
        except ValueError as exc:
            return False, str(exc)
        result = _run_command(cmd, timeout=60)
        if result.returncode == 0:
            return True, f"Container '{CONTAINER_NAME}' created."
        if _storage_limit_unsupported(result.stderr):
            try:
                cmd = _build_run_command(image_name, include_storage_limit=False)
            except ValueError as exc:
                return False, str(exc)
            result = _run_command(cmd, timeout=60)
            if result.returncode == 0:
                return True, f"Container '{CONTAINER_NAME}' created (no storage quota)."
        return False, result.stderr.strip()

    try:
        cmd = _build_run_command(image_name, include_storage_limit=False)
    except ValueError as exc:
        return False, str(exc)
    result = _run_command(cmd, timeout=60)
    if result.returncode == 0:
        return True, f"Container '{CONTAINER_NAME}' created."
    return False, result.stderr.strip()


def _wait_for_container_running(timeout_s: float = 10.0) -> tuple[bool, str]:
    """Poll until the container reaches 'running' state or the timeout expires.

    Returns False if the container enters a restart loop (crashes immediately)
    so the caller can report a meaningful error rather than getting a confusing
    'Container is restarting' error from docker exec.
    """
    deadline = time.time() + timeout_s
    consecutive_restarting = 0
    while time.time() < deadline:
        state = _inspect_container()
        if state is None:
            return False, "Container disappeared after creation."
        status = state.get("status", "").lower()
        if state.get("running"):
            return True, "running"
        if status == "restarting":
            consecutive_restarting += 1
            if consecutive_restarting >= 3:
                # Seen restarting 3 times in a row → crash-loop
                result = _run_command(
                    ["docker", "logs", "--tail", "20", CONTAINER_NAME], timeout=10
                )
                tail = (result.stdout or result.stderr or "").strip()
                hint = f"\nLast container logs:\n{tail}" if tail else ""
                return False, f"Container is crash-looping (status=restarting).{hint}"
        else:
            consecutive_restarting = 0
        time.sleep(0.5)
    return False, f"Container did not reach 'running' within {timeout_s}s."


def restart_container() -> tuple[bool, str]:
    docker_ok, docker_message = _ensure_docker_running()
    if not docker_ok:
        return False, docker_message
    if not _container_exists():
        return _ensure_container_running()
    result = _run_command(["docker", "restart", CONTAINER_NAME], timeout=60)
    if result.returncode == 0:
        return True, f"Container '{CONTAINER_NAME}' restarted."
    return False, result.stderr.strip() or "Failed to restart container."


def remove_container() -> tuple[bool, str]:
    docker_ok, docker_message = _ensure_docker_running()
    if not docker_ok:
        return False, docker_message
    if not _container_exists():
        return True, "Container does not exist."
    result = _run_command(["docker", "rm", "-f", CONTAINER_NAME], timeout=60)
    if result.returncode == 0:
        return True, f"Container '{CONTAINER_NAME}' removed."
    return False, result.stderr.strip() or "Failed to remove container."


def snapshot_image_name(name: str) -> str:
    safe_name = "".join(
        char if char.isalnum() or char in ("-", "_", ".") else "-" for char in name
    ).strip("-")
    safe_name = safe_name or "stable"
    return f"{SNAPSHOT_IMAGE_PREFIX}:{safe_name}"


def _snapshot_check_result(
    name: str,
    ok: bool,
    *,
    message: str = "",
    details: dict | None = None,
) -> dict:
    return {
        "name": name,
        "ok": ok,
        "message": message,
        "details": details or {},
    }


def _run_snapshot_preflight() -> dict:
    """Run safety/stability checks before mutating Docker snapshot state."""
    checks: list[dict] = []

    def add(name: str, ok: bool, message: str = "", details: dict | None = None) -> None:
        checks.append(_snapshot_check_result(name, ok, message=message, details=details))

    health_ok, health_message = healthcheck_container_supervisor(timeout_s=5)
    add("supervisor_healthcheck", health_ok, health_message)

    if not health_ok:
        return {"ok": False, "checks": checks}

    workspace_jobs = _docker_exec_shell(
        f"test ! -e {shlex.quote(MODEL_WORKSPACE_CONTAINER)}/.sandbox_jobs",
        timeout=10,
    )
    add(
        "job_state_outside_workspace",
        workspace_jobs.returncode == 0,
        (
            "No model-writable .sandbox_jobs under workspace."
            if workspace_jobs.returncode == 0
            else "Workspace contains .sandbox_jobs; refusing to snapshot runtime state."
        ),
    )

    job_root_probe = _docker_exec_shell(
        (
            f"{shlex.quote(SUPERVISOR_VENV)}/bin/python - <<'PY'\n"
            "import os, sys\n"
            "os.environ.setdefault('SANDBOX_IN_CONTAINER', '1')\n"
            f"os.environ.setdefault('SANDBOX_SUPERVISOR_SRC', {SUPERVISOR_SRC!r})\n"
            f"sys.path.insert(0, {SUPERVISOR_SRC!r})\n"
            "from sandbox.exec import job_root\n"
            "root = job_root()\n"
            "print(root)\n"
            "raise SystemExit(0 if str(root).startswith('/tmp/') and not root.is_symlink() else 1)\n"
            "PY"
        ),
        timeout=15,
    )
    add(
        "job_root_private",
        job_root_probe.returncode == 0,
        job_root_probe.stdout.strip() or job_root_probe.stderr.strip(),
    )

    cap_probe = _exec_bash_docker(
        "python3 - <<'PY'\nprint('A' * 120000)\nPY",
        timeout_s=15,
        background="never",
    )
    cap_stdout = str(cap_probe.get("stdout") or "")
    add(
        "stdout_cap_head_tail",
        bool(cap_probe.get("truncated")) and "[output truncated:" in cap_stdout,
        "Large stdout is bounded and marked.",
        {
            "exit_code": cap_probe.get("exit_code"),
            "stdout_bytes": len(cap_stdout.encode("utf-8", errors="replace")),
            "truncated": cap_probe.get("truncated"),
        },
    )

    invalid_utf8_probe = _exec_bash_docker(
        "python3 - <<'PY'\nimport sys\nsys.stdout.buffer.write(bytes([0xff, 0xfe, 0xfd]) + b' ok\\n')\nPY",
        timeout_s=15,
        background="never",
    )
    add(
        "invalid_utf8_replace",
        invalid_utf8_probe.get("exit_code") == 0 and "ok" in str(invalid_utf8_probe.get("stdout") or ""),
        "Invalid UTF-8 does not crash output readers.",
        {"exit_code": invalid_utf8_probe.get("exit_code")},
    )

    bg_probe = _exec_bash_docker(
        "sleep 2; printf background-ok",
        timeout_s=1,
        background="always",
    )
    job_id = bg_probe.get("job_id")
    bg_ok = bool(job_id) and bg_probe.get("error_type") == "backgrounded"
    fg_ok = False
    fg_details: dict = {"job_id": job_id}
    if job_id:
        time.sleep(2.3)
        try:
            fg_result = foreground_background_job(str(job_id))
            fg_stdout = str(fg_result.get("new_stdout") or "")
            fg_ok = fg_result.get("status") == "done" and "background-ok" in fg_stdout
            fg_details.update(
                {
                    "status": fg_result.get("status"),
                    "exit_code": fg_result.get("exit_code"),
                    "stdout": fg_stdout,
                }
            )
            JOB_REGISTRY.remove(str(job_id), cleanup=False)
        except Exception as exc:
            fg_details["error"] = str(exc)
    add(
        "background_job_lifecycle",
        bg_ok and fg_ok,
        "Background job can be tracked and foregrounded.",
        fg_details,
    )

    ok = all(check["ok"] for check in checks)
    return {"ok": ok, "checks": checks}


def snapshot_container(name: str = "stable", *, preflight: bool = True) -> dict:
    container_ok, message = _ensure_container_running()
    if not container_ok:
        return {"ok": False, "error": message}
    preflight_result: dict | None = None
    if preflight:
        preflight_result = _run_snapshot_preflight()
        if not preflight_result.get("ok"):
            failed = [
                check["name"]
                for check in preflight_result.get("checks", [])
                if not check.get("ok")
            ]
            return {
                "ok": False,
                "error": (
                    "Snapshot preflight failed; docker commit was not executed. "
                    f"Failed checks: {', '.join(failed) or 'unknown'}."
                ),
                "preflight": preflight_result,
            }
    image_name = snapshot_image_name(name)
    result = _run_command(["docker", "commit", CONTAINER_NAME, image_name], timeout=600)
    if result.returncode != 0:
        return {
            "ok": False,
            "error": result.stderr.strip() or "Failed to snapshot container.",
            "preflight": preflight_result,
        }
    return {
        "ok": True,
        "snapshot_image": image_name,
        "name": name,
        "preflight": preflight_result,
    }


def reset_container(preserve_workspace: bool = True) -> dict:
    remove_ok, remove_message = remove_container()
    if not remove_ok:
        return {"ok": False, "error": remove_message}

    wiped_entries: list[str] = []
    if not preserve_workspace:
        root = task_root()
        if root.exists():
            for item in root.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                    wiped_entries.append(item.name)
                except OSError as exc:
                    return {"ok": False, "error": f"Failed to wipe workspace entry '{item.name}': {exc}"}

    ensure_ok, ensure_message = _ensure_container_running()
    if not ensure_ok:
        return {"ok": False, "error": ensure_message}

    result: dict = {
        "ok": True,
        "message": "Container recreated from base image.",
        "preserve_workspace": preserve_workspace,
    }
    if not preserve_workspace:
        result["wiped_entries"] = wiped_entries
    return result


def restore_container(name: str = "stable", preserve_workspace: bool = True) -> dict:
    docker_ok, docker_message = _ensure_docker_running()
    if not docker_ok:
        return {"ok": False, "error": docker_message}
    image_name = snapshot_image_name(name)
    inspect_result = _run_command(
        ["docker", "image", "inspect", image_name], timeout=20
    )
    if inspect_result.returncode != 0:
        return {"ok": False, "error": f"Snapshot image not found: {image_name}"}
    remove_ok, remove_message = remove_container()
    if not remove_ok:
        return {"ok": False, "error": remove_message}
    ensure_ok, ensure_message = _ensure_container_running(image_name=image_name)
    if not ensure_ok:
        return {"ok": False, "error": ensure_message}
    return {
        "ok": True,
        "message": f"Container restored from snapshot '{name}'.",
        "snapshot_image": image_name,
        "preserve_workspace": preserve_workspace,
    }


# ── Supervisor stdio proxy ───────────────────────────────────────────

def _supervisor_exec_command(
    *,
    interactive: bool = True,
    supervisor_args: list[str] | None = None,
) -> list[str]:
    command = ["docker", "exec"]
    if interactive:
        command.append("-i")
    command.extend([
        "-u", "root",
        "-w", MODEL_WORKSPACE_CONTAINER,
        "-e", "SANDBOX_IN_CONTAINER=1",
        "-e", f"SANDBOX_COMMAND_USER={COMMAND_USER}",
        "-e", f"SANDBOX_HOST_WORKSPACE={CONTAINER_WORKSPACE}",
        "-e", f"SANDBOX_DEFAULT_TASK_DIR={DEFAULT_TASK_DIR}",
        "-e", f"SANDBOX_SUPERVISOR_SRC={SUPERVISOR_SRC}",
        "-e", f"SANDBOX_SUPERVISOR_VENV={SUPERVISOR_VENV}",
        "-e", f"PYTHONPATH={SUPERVISOR_SRC}",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        CONTAINER_NAME,
        f"{SUPERVISOR_VENV}/bin/python",
        "-m", "sandbox.supervisor",
    ])
    command.extend(supervisor_args or [])
    return command


def start_container_supervisor() -> subprocess.Popen:
    return subprocess.Popen(
        _supervisor_exec_command(interactive=True),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def healthcheck_container_supervisor(timeout_s: int = 3) -> tuple[bool, str]:
    try:
        result = _run_command(
            _supervisor_exec_command(
                interactive=False, supervisor_args=["--healthcheck"]
            ),
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return False, f"Supervisor healthcheck timed out after {timeout_s}s."
    except Exception as exc:
        return False, str(exc)

    stdout = result.stdout.strip()
    if result.returncode == 0 and stdout == SUPERVISOR_PONG:
        return True, stdout
    if result.returncode == 0 and stdout == "sandbox-supervisor-pong":
        return False, "Supervisor version mismatch: image needs rebuild (got v1 pong, expected v2)."
    message = result.stderr.strip() or stdout or f"Exit code: {result.returncode}"
    return False, message


def _supervisor_python_missing(message: str) -> bool:
    lowered = message.lower()
    expected_python = f"{SUPERVISOR_VENV}/bin/python".lower()
    return expected_python in lowered and "no such file or directory" in lowered


def ensure_supervisor_ready(
    *,
    attempts: int = 2,
    timeout_s: int = 3,
    recreate_on_failure: bool = True,
) -> tuple[bool, str]:
    last_error = ""
    for attempt in range(max(1, attempts)):
        ok, message = healthcheck_container_supervisor(timeout_s=timeout_s)
        if ok:
            return True, message
        last_error = message
        if attempt + 1 < attempts:
            time.sleep(0.2)

    if not recreate_on_failure:
        return False, last_error

    with _container_lock:
        removed, remove_message = _force_remove()
        if not removed:
            return False, f"Supervisor failed ({last_error}); recreate failed: {remove_message}"
        created, create_message = _create_container(SANDBOX_IMAGE)
        if not created:
            return False, f"Supervisor failed ({last_error}); recreate failed: {create_message}"

    running, run_msg = _wait_for_container_running(timeout_s=15.0)
    if not running:
        return False, f"Supervisor failed ({last_error}); container did not start: {run_msg}"

    for attempt in range(max(1, attempts)):
        ok, message = healthcheck_container_supervisor(timeout_s=timeout_s)
        if ok:
            return True, f"Supervisor recovered after recreate: {message}"
        last_error = message
        if attempt + 1 < attempts:
            time.sleep(0.2)

    if _supervisor_python_missing(last_error):
        with _container_lock:
            removed, remove_message = _force_remove()
            if not removed:
                return False, (
                    f"Supervisor venv is missing ({last_error}); "
                    f"container remove failed: {remove_message}"
                )
            rebuilt, rebuild_message = _ensure_image(force_rebuild=True)
            if not rebuilt:
                return False, (
                    f"Supervisor venv is missing ({last_error}); "
                    f"image rebuild failed: {rebuild_message}"
                )
            created, create_message = _create_container(SANDBOX_IMAGE)
            if not created:
                return False, (
                    f"Supervisor venv is missing ({last_error}); "
                    f"container recreate after rebuild failed: {create_message}"
                )

        running, run_msg = _wait_for_container_running(timeout_s=15.0)
        if not running:
            return False, (
                f"Supervisor venv was missing ({last_error}); "
                f"container did not start after rebuild: {run_msg}"
            )

        for attempt in range(max(1, attempts)):
            ok, message = healthcheck_container_supervisor(timeout_s=timeout_s)
            if ok:
                return True, f"Supervisor recovered after image rebuild: {message}"
            last_error = message
            if attempt + 1 < attempts:
                time.sleep(0.2)

    return False, f"Supervisor healthcheck failed after recreate: {last_error}"


def _read_pipe_chunk(source) -> bytes:
    if hasattr(source, "read1"):
        return source.read1(8192)
    if hasattr(source, "readline"):
        return source.readline()
    return source.read(8192)


def _forward_binary_stream(source, sink, close_sink: bool = False) -> None:
    try:
        while True:
            chunk = _read_pipe_chunk(source)
            if not chunk:
                break
            sink.write(chunk)
            sink.flush()
    except (BrokenPipeError, OSError):
        pass
    finally:
        if close_sink:
            try:
                sink.close()
            except OSError:
                pass


def _read_stdin_to_queue(
    input_stream, input_queue: Queue, eof: threading.Event
) -> None:
    try:
        while True:
            chunk = _read_pipe_chunk(input_stream)
            if not chunk:
                break
            input_queue.put(chunk)
    finally:
        eof.set()
        input_queue.put(None)


def _write_queue_to_process(
    input_queue: Queue,
    process: subprocess.Popen,
    eof: threading.Event,
) -> None:
    if process.stdin is None:
        return
    try:
        while process.poll() is None:
            try:
                chunk = input_queue.get(timeout=0.1)
            except Empty:
                continue
            if chunk is None:
                try:
                    process.stdin.close()
                except OSError:
                    pass
                return
            try:
                process.stdin.write(chunk)
                process.stdin.flush()
            except (BrokenPipeError, OSError):
                return
    finally:
        if eof.is_set():
            try:
                process.stdin.close()
            except OSError:
                pass


def pipe_to_container_supervisor(
    *,
    max_restarts: int | None = None,
    input_stream=None,
    output_stream=None,
    error_stream=None,
) -> int:
    """Pipe host stdio to the in-container MCP supervisor with reconnect."""
    input_stream = input_stream or sys.stdin.buffer
    output_stream = output_stream or sys.stdout.buffer
    error_stream = error_stream or sys.stderr.buffer
    input_queue: Queue | None = None
    stdin_eof: threading.Event | None = None
    stdin_thread = None

    def _ensure_stdin_reader() -> tuple[Queue, threading.Event]:
        nonlocal input_queue, stdin_eof, stdin_thread
        if input_queue is None or stdin_eof is None:
            input_queue = Queue()
            stdin_eof = threading.Event()
            stdin_thread = threading.Thread(
                target=_read_stdin_to_queue,
                args=(input_stream, input_queue, stdin_eof),
                daemon=True,
            )
            stdin_thread.start()
        return input_queue, stdin_eof

    _ensure_sandbox_config()

    restarts = 0
    last_returncode = 1
    while max_restarts is None or restarts <= max_restarts:
        container_ok, message = _ensure_container_running()
        if not container_ok:
            error_stream.write((message + "\n").encode("utf-8", errors="replace"))
            error_stream.flush()
            return 1

        supervisor_ok, supervisor_message = ensure_supervisor_ready()
        if not supervisor_ok:
            error_stream.write(
                (supervisor_message + "\n").encode("utf-8", errors="replace")
            )
            error_stream.flush()
            return 1

        input_queue, stdin_eof = _ensure_stdin_reader()
        process = start_container_supervisor()
        stdout_thread = threading.Thread(
            target=_forward_binary_stream,
            args=(process.stdout, output_stream),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_forward_binary_stream,
            args=(process.stderr, error_stream),
            daemon=True,
        )
        writer_thread = threading.Thread(
            target=_write_queue_to_process,
            args=(input_queue, process, stdin_eof),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        writer_thread.start()

        last_returncode = process.wait()
        for pipe in (process.stdout, process.stderr):
            try:
                if pipe is not None:
                    pipe.close()
            except OSError:
                pass
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        writer_thread.join(timeout=5)

        if stdin_eof.is_set():
            return last_returncode

        restarts += 1
        error_stream.write(
            f"mcp-sandbox supervisor exited with {last_returncode}; restarting.\n"
            .encode("utf-8", errors="replace")
        )
        error_stream.flush()
        time.sleep(0.2)

    return last_returncode


# ── Docker-exec bash backend (host-side fallback) ────────────────────
# Used when IN_CONTAINER=False. Will be removed after full migration.

def _docker_exec_shell(
    script: str,
    *,
    container_cwd: str | None = None,
    timeout: int = 30,
    user: str | None = None,
):
    args = ["docker", "exec"]
    if user:
        args.extend(["-u", user])
    if container_cwd:
        args.extend(["-w", container_cwd])
    args.extend([CONTAINER_NAME, "bash", "-lc", script])
    return _run_command(args, timeout=timeout)


def _read_docker_job_file(
    job: BackgroundJob, stream: str, *, incremental: bool = True
) -> str:
    if job.container_job_dir is None:
        return ""
    path = f"{job.container_job_dir.rstrip('/')}/{stream}"
    result = _docker_exec_shell(
        f"cat {shlex.quote(path)} 2>/dev/null || true", timeout=10
    )
    content = result.stdout if result.returncode == 0 else ""
    if not incremental:
        return content
    offset_attr = f"{stream}_offset"
    offset = int(getattr(job, offset_attr))
    new_content = content[offset:]
    setattr(job, offset_attr, len(content))
    return new_content


def _refresh_docker_job(job: BackgroundJob) -> BackgroundJob:
    if job.runtime != "docker" or job.container_job_dir is None:
        return job
    job_dir = shlex.quote(job.container_job_dir)
    result = _docker_exec_shell(
        (
            f"cat {job_dir}/status 2>/dev/null || echo running; "
            f"cat {job_dir}/exit_code 2>/dev/null || true"
        ),
        timeout=10,
    )
    if result.returncode != 0:
        return job
    lines = result.stdout.splitlines()
    status = lines[0].strip() if lines else job.status
    exit_code = job.exit_code
    if len(lines) > 1 and lines[1].strip():
        try:
            exit_code = int(lines[1].strip())
        except ValueError:
            exit_code = job.exit_code
    if status == "done":
        JOB_REGISTRY.mark_done(job.job_id, exit_code)
    elif status == "killed":
        JOB_REGISTRY.mark_killed(job.job_id)
    elif status:
        job.status = status
    return job


def list_background_jobs() -> dict:
    for job in JOB_REGISTRY.list_jobs():
        if job.get("runtime") == "docker" and job.get("status") == "running":
            try:
                _refresh_docker_job(JOB_REGISTRY.get(job["job_id"]))
            except Exception:
                pass
    return {"jobs": JOB_REGISTRY.list_jobs()}


def foreground_background_job(job_id: str) -> dict:
    job = _refresh_docker_job(JOB_REGISTRY.get(job_id))
    stdout = _read_docker_job_file(job, "stdout", incremental=True)
    stderr = _read_docker_job_file(job, "stderr", incremental=True)
    stdout, trunc_out = _truncate(stdout)
    stderr, trunc_err = _truncate(stderr)
    return {
        **job.to_result(),
        "new_stdout": stdout,
        "new_stderr": stderr,
        "truncated": trunc_out or trunc_err,
    }


def kill_background_job(job_id: str) -> dict:
    job = JOB_REGISTRY.get(job_id)
    if job.runtime == "docker" and job.container_job_dir:
        job_dir = shlex.quote(job.container_job_dir)
        _docker_exec_shell(
            f"kill $(cat {job_dir}/pid 2>/dev/null) >/dev/null 2>&1 || true; "
            f"echo killed > {job_dir}/status",
            timeout=10,
        )
    JOB_REGISTRY.mark_killed(job.job_id)
    return job.to_result()


def _exec_bash_docker_background(
    command: str,
    cwd: str,
    timeout_s: int,
    container_cwd: str,
    on_progress: Callable[[float, str], None] | None = None,
) -> dict:
    start_time = time.time()
    job_id = _new_background_job_id()
    job_dir: str | None = None
    candidate_roots = " ".join(shlex.quote(item) for item in _docker_job_root_candidates())
    command_quoted = shlex.quote(command)
    wrapper = (
        f"bash -lc {command_quoted}; "
        "code=$?; "
        "echo $code > \"$job_dir/exit_code\"; "
        "echo done > \"$job_dir/status\""
    )
    setup_script = (
        f"job_root=''; "
        f"for candidate in {candidate_roots}; do "
        f"  candidate=$(eval echo \"$candidate\"); "
        f"  if mkdir -p \"$candidate\" >/dev/null 2>&1 && [ -w \"$candidate\" ]; then "
        f"    job_root=\"$candidate\"; break; "
        f"  fi; "
        f"done; "
        f"if [ -z \"$job_root\" ]; then "
        f"  echo 'Failed to find writable background job root.' >&2; exit 1; "
        f"fi; "
        f"job_dir=\"$job_root/{job_id}\"; "
        f"mkdir -p \"$job_dir\"; "
        f": > \"$job_dir/stdout\"; "
        f": > \"$job_dir/stderr\"; "
        f"echo running > \"$job_dir/status\"; "
        f"export job_dir; "
        f"nohup bash -lc {shlex.quote(wrapper)} "
        f"> \"$job_dir/stdout\" 2> \"$job_dir/stderr\" < /dev/null & "
        f"echo \"$job_dir\"; "
        f"echo $! > \"$job_dir/pid\"; "
        f"cat \"$job_dir/pid\""
    )
    setup = _docker_exec_shell(
        setup_script,
        container_cwd=container_cwd,
        timeout=30,
        user=COMMAND_USER if COMMAND_USER and COMMAND_USER != "root" else None,
    )
    if setup.returncode != 0:
        return {
            "exit_code": None,
            "stdout": setup.stdout,
            "stderr": setup.stderr,
            "error": setup.stderr.strip() or "Failed to start background job.",
            "elapsed_ms": int((time.time() - start_time) * 1000),
            "truncated": False,
            "cwd": normalize_model_relative_path(cwd),
        }

    setup_lines = [line.strip() for line in setup.stdout.splitlines() if line.strip()]
    if setup_lines:
        maybe_job_dir = setup_lines[0]
        if "/" in maybe_job_dir:
            job_dir = maybe_job_dir
    try:
        pid = int(setup_lines[-1])
    except (ValueError, IndexError):
        pid = None

    job = JOB_REGISTRY.create(
        command=command,
        cwd=normalize_model_relative_path(cwd),
        runtime="docker",
        pid=pid,
        container_job_dir=job_dir or f"{_resolve_docker_job_root()}/{job_id}",
        job_id=job_id,
    )

    while True:
        job = _refresh_docker_job(job)
        if job.status != "running":
            stdout = _read_docker_job_file(job, "stdout", incremental=False)
            stderr = _read_docker_job_file(job, "stderr", incremental=False)
            stdout, trunc_out = _truncate(stdout)
            stderr, trunc_err = _truncate(stderr)
            if on_progress is not None:
                on_progress(100.0, f"Bash finished in {normalize_model_relative_path(cwd)}")
            return {
                "exit_code": job.exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "error": None if job.exit_code == 0 else f"Exit code: {job.exit_code}",
                "elapsed_ms": int((time.time() - start_time) * 1000),
                "truncated": trunc_out or trunc_err,
                "cwd": normalize_model_relative_path(cwd),
            }

        elapsed_s = time.time() - start_time
        if elapsed_s >= timeout_s:
            stdout = _read_docker_job_file(job, "stdout", incremental=True)
            stderr = _read_docker_job_file(job, "stderr", incremental=True)
            stdout, trunc_out = _truncate(stdout)
            stderr, trunc_err = _truncate(stderr)
            return _background_error_result(
                job=job,
                stdout=stdout,
                stderr=stderr,
                start_time=start_time,
                timeout_s=timeout_s,
                cwd=cwd,
                truncated=trunc_out or trunc_err,
            )
        if on_progress is not None:
            progress = min(95.0, max(5.0, (elapsed_s / timeout_s) * 90.0))
            on_progress(progress, f"Running bash in {normalize_model_relative_path(cwd)}")
        time.sleep(0.2)


def _exec_bash_docker(
    command: str,
    cwd: str = ".",
    timeout_s: int = DEFAULT_TIMEOUT,
    stdin: str | None = None,
    on_stdout: Callable[[str], None] | None = None,
    on_stderr: Callable[[str], None] | None = None,
    on_progress: Callable[[float, str], None] | None = None,
    background: str | bool | None = "never",
) -> dict:
    """Execute a bash command inside the sandbox container via docker exec."""
    from sandbox.exec import should_use_background

    command = _rewrite_legacy_upload_paths(command)

    if timeout_s <= 0:
        raise ValueError("timeout_s must be greater than 0.")

    target_dir = get_secure_task_path(cwd, kind="cwd")
    if not target_dir.exists():
        raise FileNotFoundError(f"cwd not found: {normalize_model_relative_path(cwd)}")
    if not target_dir.is_dir():
        raise NotADirectoryError(
            f"cwd is not a directory: {normalize_model_relative_path(cwd)}"
        )

    container_ok, container_message = _ensure_container_running()
    if not container_ok:
        return {
            "ok": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": container_message,
            "elapsed_ms": 0,
            "truncated": False,
        }

    relative_cwd = (
        target_dir.relative_to(task_root()).as_posix()
        if target_dir != task_root()
        else ""
    )
    container_cwd = MODEL_WORKSPACE_CONTAINER
    if relative_cwd:
        container_cwd = f"{MODEL_WORKSPACE_CONTAINER}/{relative_cwd}"

    if stdin is None and should_use_background(command, timeout_s, background):
        return _exec_bash_docker_background(
            command=command,
            cwd=cwd,
            timeout_s=timeout_s,
            container_cwd=container_cwd,
            on_progress=on_progress,
        )

    start_time = time.time()
    exec_cmd = ["docker", "exec", "-i"]
    if COMMAND_USER and COMMAND_USER != "root":
        exec_cmd.extend(["-u", COMMAND_USER])
    exec_cmd.extend([
        "-w", container_cwd,
        "-e", "PYTHONIOENCODING=utf-8",
        "-e", "LANG=C.UTF-8",
        "-e", f"SANDBOX_DEFAULT_TASK_DIR={DEFAULT_TASK_DIR}",
        CONTAINER_NAME, "bash", "-lc", command,
    ])

    try:
        process = subprocess.Popen(
            exec_cmd,
            stdin=subprocess.PIPE if stdin is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
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

    if stdin is not None and process.stdin is not None:
        try:
            process.stdin.write(stdin)
        except BrokenPipeError:
            pass
        finally:
            process.stdin.close()

    try:
        while process.poll() is None:
            elapsed_s = time.time() - start_time
            if elapsed_s >= timeout_s:
                process.kill()
                raise subprocess.TimeoutExpired(exec_cmd, timeout_s)
            if on_progress is not None:
                progress = min(95.0, max(5.0, (elapsed_s / timeout_s) * 90.0))
                on_progress(
                    progress, f"Running bash in {normalize_model_relative_path(cwd)}"
                )
            time.sleep(0.2)

        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)
        stdout_value, trunc_out = stdout_chunks.value()
        stderr_value, trunc_err = stderr_chunks.value()
        restart_container()
        return {
            "exit_code": None,
            "stdout": stdout_value,
            "stderr": stderr_value,
            "error": (
                f"Execution timed out after {timeout_s} seconds. "
                "Container restarted to free resources."
            ),
            "elapsed_ms": int((time.time() - start_time) * 1000),
            "truncated": trunc_out or trunc_err,
            "cwd": normalize_model_relative_path(cwd),
        }

    stdout_value, trunc_out = stdout_chunks.value()
    stderr_value, trunc_err = stderr_chunks.value()

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


# ── Status reporting ─────────────────────────────────────────────────

def get_status() -> dict:
    """Return Docker and container status without forcing startup."""
    docker_cli = _docker_cli_available()
    docker_daemon_running = False
    docker_info_message = "Docker CLI not found."
    daemon_details = None

    if docker_cli:
        try:
            info_result = _docker_info(timeout=5)
            if info_result.returncode == 0:
                docker_daemon_running = True
                docker_info_message = "Docker daemon is running."
                try:
                    daemon_details = json.loads(info_result.stdout)
                except json.JSONDecodeError:
                    daemon_details = None
            else:
                docker_info_message = (
                    info_result.stderr.strip() or "Docker daemon is not running."
                )
        except Exception as exc:
            docker_info_message = str(exc)

    container_status = "not found"
    container_running = False
    if docker_daemon_running:
        ps_result = _run_command(
            ["docker", "ps", "-a",
             "--filter", f"name=^{CONTAINER_NAME}$",
             "--format", "{{.Status}}"],
            timeout=10,
        )
        if ps_result.stdout.strip():
            container_status = ps_result.stdout.strip()
            container_running = container_status.lower().startswith("up")

    task_dir = task_root()
    task_entries: list[str] = []
    task_exists = task_dir.exists()
    if task_exists:
        try:
            task_entries = sorted(item.name for item in task_dir.iterdir())
        except OSError:
            task_entries = []

    from sandbox.config import (
        CPU_LIMIT, MEMORY_LIMIT, MEMORY_SWAP_LIMIT,
        NETWORK_LIMIT_MBIT, PIDS_LIMIT, STORAGE_LIMIT, THREAD_LIMIT,
    )

    return {
        "ok": True,
        "docker_cli_available": docker_cli,
        "docker_daemon_running": docker_daemon_running,
        "docker_message": docker_info_message,
        "container_name": CONTAINER_NAME,
        "container_status": container_status,
        "container_running": container_running,
        "image": SANDBOX_IMAGE,
        "workspace_host": HOST_WORKSPACE,
        "workspace_container": CONTAINER_WORKSPACE,
        "model_workspace_host": str(task_root()),
        "model_workspace_container": MODEL_WORKSPACE_CONTAINER,
        "task_dir_exists": task_exists,
        "task_entry_count": len(task_entries),
        "task_entry_sample": task_entries[:20],
        "bash_default_cwd": ".",
        "limits": {
            "cpus": CPU_LIMIT,
            "threads": THREAD_LIMIT,
            "memory": MEMORY_LIMIT,
            "memory_swap": MEMORY_SWAP_LIMIT,
            "pids_limit": PIDS_LIMIT,
            "storage_limit": STORAGE_LIMIT,
            "network_limit_mbit": NETWORK_LIMIT_MBIT,
        },
        "docker_server_version": (daemon_details or {}).get("ServerVersion"),
        "docker_driver": (daemon_details or {}).get("Driver"),
    }
