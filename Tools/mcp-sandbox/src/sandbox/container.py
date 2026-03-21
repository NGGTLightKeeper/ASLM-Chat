# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from sandbox.config import (
    CONTAINER_NAME,
    CONTAINER_WORKSPACE,
    CPU_LIMIT,
    DEFAULT_TASK_DIR,
    DEFAULT_TIMEOUT,
    DOCKER_START_TIMEOUT_SECONDS,
    HOST_WORKSPACE,
    HTTP_PORT,
    MAX_OUTPUT_CHARS,
    MEMORY_LIMIT,
    MEMORY_SWAP_LIMIT,
    PIDS_LIMIT,
    SANDBOX_IMAGE,
    SANDBOX_IMAGE_SOURCE,
    SNAPSHOT_IMAGE_PREFIX,
    STORAGE_LIMIT,
    WINDOWS_DOCKER_DESKTOP_PATHS,
)
from sandbox.workspace import get_secure_task_path, normalize_relative_path, task_root


# Output helpers.

def _truncate(value: str | None) -> tuple[str, bool]:
    """Trim output while keeping the tail."""

    if value is None:
        return "", False

    if len(value) <= MAX_OUTPUT_CHARS:
        return value, False

    return value[-MAX_OUTPUT_CHARS:], True


# Command execution.

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
        timeout=timeout,
        check=check,
    )


# Docker availability checks.

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


# Container existence checks.

def _container_exists() -> bool:
    """Return True when the sandbox container exists."""

    result = _run_command(
        ["docker", "ps", "-aq", "-f", f"name=^{CONTAINER_NAME}$"],
        timeout=10,
    )
    return bool(result.stdout.strip())


def _container_is_running() -> bool:
    """Return True when the sandbox container is running."""

    result = _run_command(
        ["docker", "ps", "-q", "-f", f"name=^{CONTAINER_NAME}$"],
        timeout=10,
    )
    return bool(result.stdout.strip())


# Image preparation.

def _ensure_image() -> tuple[bool, str]:
    """Ensure the sandbox image exists locally."""

    inspect_result = _run_command(
        ["docker", "image", "inspect", SANDBOX_IMAGE],
        timeout=20,
    )
    if inspect_result.returncode == 0:
        return True, "Image already exists locally."

    dockerfile_dir = Path(__file__).resolve().parents[2]
    dockerfile_path = dockerfile_dir / "Dockerfile"

    def _build_local() -> tuple[bool, str]:
        if not dockerfile_path.exists():
            return False, f"Dockerfile not found at: {dockerfile_path}"

        build_result = _run_command(
            ["docker", "build", "-t", SANDBOX_IMAGE, str(dockerfile_dir)],
            timeout=1800,
        )
        if build_result.returncode != 0:
            return False, build_result.stderr.strip() or "Failed to build sandbox image."
        return True, f"Image '{SANDBOX_IMAGE}' built locally from Dockerfile."

    def _pull_registry() -> tuple[bool, str]:
        pull_result = _run_command(["docker", "pull", SANDBOX_IMAGE], timeout=600)
        if pull_result.returncode != 0:
            return False, pull_result.stderr.strip() or "Failed to pull sandbox image from Docker Hub."
        return True, f"Image '{SANDBOX_IMAGE}' pulled from Docker Hub."

    source = SANDBOX_IMAGE_SOURCE if SANDBOX_IMAGE_SOURCE in {"local", "registry", "auto"} else "local"
    if source == "local":
        local_ok, local_message = _build_local()
        if local_ok:
            return True, local_message

        registry_ok, registry_message = _pull_registry()
        if registry_ok:
            return True, f"{local_message} Falling back to registry succeeded: {registry_message}"
        return False, f"{local_message} Registry fallback failed: {registry_message}"

    if source == "registry":
        registry_ok, registry_message = _pull_registry()
        if registry_ok:
            return True, registry_message

        local_ok, local_message = _build_local()
        if local_ok:
            return True, f"{registry_message} Falling back to local build succeeded: {local_message}"
        return False, f"{registry_message} Local build fallback failed: {local_message}"

    registry_ok, registry_message = _pull_registry()
    if registry_ok:
        return True, registry_message

    local_ok, local_message = _build_local()
    if local_ok:
        return True, f"{registry_message} Falling back to local build succeeded: {local_message}"
    return False, f"{registry_message} Local build fallback failed: {local_message}"


# Container start command.

def _build_run_command(
    image_name: str,
    include_storage_limit: bool = True,
) -> list[str]:
    """Build the docker run command for the sandbox container."""

    command = [
        "docker",
        "run",
        "-d",
        "--name",
        CONTAINER_NAME,
        "--restart",
        "unless-stopped",
        "--cpus",
        CPU_LIMIT,
        "--memory",
        MEMORY_LIMIT,
        "--memory-swap",
        MEMORY_SWAP_LIMIT,
        "--pids-limit",
        PIDS_LIMIT,
        "--no-healthcheck",
    ]

    if include_storage_limit and STORAGE_LIMIT:
        command.extend(["--storage-opt", f"size={STORAGE_LIMIT}"])

    command.extend(["--gpus", "all"])

    task_host_path = os.path.join(HOST_WORKSPACE, DEFAULT_TASK_DIR)
    os.makedirs(task_host_path, exist_ok=True)

    command.extend(
        [
            "-v",
            f"{task_host_path}:{CONTAINER_WORKSPACE}",
            "-w",
            CONTAINER_WORKSPACE,
            image_name,
            "tail",
            "-f",
            "/dev/null",
        ]
    )
    return command


def _storage_limit_unsupported(stderr_text: str) -> bool:
    """Return True for storage quota support errors."""

    lowered = stderr_text.lower()
    indicators = [
        "storage-opt",
        "unknown flag",
        "quota",
        "overlay2",
        "xfs",
        "not supported",
        "invalid argument",
    ]
    return any(indicator in lowered for indicator in indicators)


def _ensure_container_running(image_name: str = SANDBOX_IMAGE) -> tuple[bool, str]:
    """Ensure the sandbox container exists and is running."""

    docker_ok, docker_message = _ensure_docker_running()
    if not docker_ok:
        return False, docker_message

    if _container_is_running():
        return True, "Container is running."

    if _container_exists():
        start_result = _run_command(["docker", "start", CONTAINER_NAME], timeout=30)
        if start_result.returncode == 0:
            return True, f"Container '{CONTAINER_NAME}' started."

        return False, start_result.stderr.strip() or "Failed to start existing container."

    build_ok, build_message = _ensure_image()
    if not build_ok:
        return False, build_message

    run_result = _run_command(
        _build_run_command(
            image_name,
            include_storage_limit=bool(STORAGE_LIMIT),
        ),
        timeout=60,
    )
    if run_result.returncode == 0:
        return True, f"Container '{CONTAINER_NAME}' created and started."

    stderr_text = run_result.stderr.strip()
    if STORAGE_LIMIT and _storage_limit_unsupported(stderr_text):
        retry_result = _run_command(
            _build_run_command(image_name, include_storage_limit=False),
            timeout=60,
        )
        if retry_result.returncode == 0:
            return (
                True,
                f"Container '{CONTAINER_NAME}' created and started without "
                f"storage quota. Original limitation was unsupported: {stderr_text}",
            )

        return (
            False,
            retry_result.stderr.strip()
            or "Failed to create container without storage quota.",
        )

    return False, stderr_text or "Failed to create container."


# Container lifecycle actions.

def restart_container() -> tuple[bool, str]:
    """Restart the container."""

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
    """Remove the existing container when present."""

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
    """Build the Docker tag for a named snapshot."""

    safe_name = "".join(
        char if char.isalnum() or char in ("-", "_", ".") else "-"
        for char in name
    ).strip("-")
    safe_name = safe_name or "stable"
    return f"{SNAPSHOT_IMAGE_PREFIX}:{safe_name}"


def snapshot_container(name: str = "stable") -> dict:
    """Create a Docker image snapshot from the current container."""

    container_ok, message = _ensure_container_running()
    if not container_ok:
        return {"ok": False, "error": message}

    image_name = snapshot_image_name(name)
    result = _run_command(["docker", "commit", CONTAINER_NAME, image_name], timeout=600)
    if result.returncode != 0:
        return {
            "ok": False,
            "error": result.stderr.strip() or "Failed to snapshot container.",
        }

    return {"ok": True, "snapshot_image": image_name, "name": name}


def reset_container(preserve_workspace: bool = True) -> dict:
    """Recreate the container from the base image."""

    remove_ok, remove_message = remove_container()
    if not remove_ok:
        return {"ok": False, "error": remove_message}

    ensure_ok, ensure_message = _ensure_container_running()
    if not ensure_ok:
        return {"ok": False, "error": ensure_message}

    return {
        "ok": True,
        "message": "Container recreated from base image.",
        "preserve_workspace": preserve_workspace,
    }


def restore_container(name: str = "stable", preserve_workspace: bool = True) -> dict:
    """Restore the container from a named snapshot."""

    docker_ok, docker_message = _ensure_docker_running()
    if not docker_ok:
        return {"ok": False, "error": docker_message}

    image_name = snapshot_image_name(name)
    inspect_result = _run_command(["docker", "image", "inspect", image_name], timeout=20)
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


# Bash execution.

def exec_bash(
    command: str,
    cwd: str = ".",
    timeout_s: int = DEFAULT_TIMEOUT,
    stdin: str | None = None,
) -> dict:
    """Execute a bash command inside the sandbox container."""

    if timeout_s <= 0:
        raise ValueError("timeout_s must be greater than 0.")

    target_dir = get_secure_task_path(cwd, kind="cwd")
    if not target_dir.exists():
        raise FileNotFoundError(f"cwd not found: {normalize_relative_path(cwd)}")

    if not target_dir.is_dir():
        raise NotADirectoryError(f"cwd is not a directory: {normalize_relative_path(cwd)}")

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
    container_cwd = CONTAINER_WORKSPACE
    if relative_cwd:
        container_cwd = f"{CONTAINER_WORKSPACE}/{relative_cwd}"

    start_time = time.time()
    exec_cmd = [
        "docker",
        "exec",
        "-i",
        "-w",
        container_cwd,
        "-e",
        "PYTHONIOENCODING=utf-8",
        "-e",
        "LANG=C.UTF-8",
        CONTAINER_NAME,
        "bash",
        "-lc",
        command,
    ]

    try:
        result = _run_command(exec_cmd, timeout=timeout_s, input_text=stdin)
    except subprocess.TimeoutExpired:
        restart_container()
        return {
            "ok": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": (
                f"Execution timed out after {timeout_s} seconds. "
                "Container restarted to free resources."
            ),
            "elapsed_ms": int((time.time() - start_time) * 1000),
            "truncated": False,
        }

    stdout_value, trunc_out = _truncate(result.stdout)
    stderr_value, trunc_err = _truncate(result.stderr)

    return {
        "ok": result.returncode == 0,
        "exit_code": result.returncode,
        "stdout": stdout_value,
        "stderr": stderr_value,
        "error": None if result.returncode == 0 else f"Exit code: {result.returncode}",
        "elapsed_ms": int((time.time() - start_time) * 1000),
        "truncated": trunc_out or trunc_err,
        "cwd": normalize_relative_path(cwd),
    }


# Status reporting.

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
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name=^{CONTAINER_NAME}$",
                "--format",
                "{{.Status}}",
            ],
            timeout=10,
        )
        if ps_result.stdout.strip():
            container_status = ps_result.stdout.strip()
            container_running = container_status.lower().startswith("up")

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
        "model_workspace_container": CONTAINER_WORKSPACE,
        "bash_default_cwd": ".",
        "http_share_base_url": f"http://127.0.0.1:{HTTP_PORT}",
        "limits": {
            "cpus": CPU_LIMIT,
            "memory": MEMORY_LIMIT,
            "memory_swap": MEMORY_SWAP_LIMIT,
            "pids_limit": PIDS_LIMIT,
            "storage_limit": STORAGE_LIMIT,
        },
        "docker_server_version": (daemon_details or {}).get("ServerVersion"),
        "docker_driver": (daemon_details or {}).get("Driver"),
    }
