# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

from .config import settings
from .types import PythonExecutionResult

logger = logging.getLogger(__name__)


# Sandbox identity
CONTAINER_NAME: str = os.getenv("DEEP_THINK_SANDBOX_CONTAINER", "deep-think-sandbox")
SANDBOX_IMAGE: str = os.getenv("DEEP_THINK_SANDBOX_IMAGE", "dima1312313/deep-think-sandbox:latest")
_DOCKERFILE_DIR = Path(__file__).resolve().parents[1]
_WINDOWS_DOCKER_PATHS = [
    os.path.expandvars(r"%ProgramFiles%\Docker\Docker\Docker Desktop.exe"),
    os.path.expandvars(r"%LocalAppData%\Docker\Docker Desktop.exe"),
]
_DOCKER_START_TIMEOUT = 60


# Process helpers

# Run a subprocess and capture its output
def _run(cmd: list[str], timeout: int = 15, input_text: str | None = None) -> subprocess.CompletedProcess:
    """Run a subprocess and return the completed process object."""

    return subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )

def _truncate(text: str, limit: int = 12000) -> tuple[str, bool]:
    """Truncate long output while preserving a short tail note."""

    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]", True


# Docker daemon checks

# Check whether Docker CLI is installed
def _docker_cli_available() -> bool:
    """Return whether the Docker CLI is available on the host."""

    try:
        return _run(["docker", "--version"], timeout=5).returncode == 0
    except Exception:
        return False

def _daemon_running() -> bool:
    """Return whether the Docker daemon is reachable."""

    try:
        return _run(["docker", "info"], timeout=5).returncode == 0
    except Exception:
        return False

def _ensure_docker_running() -> tuple[bool, str]:
    """Ensure the Docker daemon is available, starting Docker Desktop on Windows when possible."""

    if not _docker_cli_available():
        return False, "Docker CLI not found. Install Docker Desktop first."

    if _daemon_running():
        return True, "Docker daemon is running."

    if os.name != "nt":
        return False, "Docker daemon is not running. Start Docker and try again."

    launched = False
    for path in _WINDOWS_DOCKER_PATHS:
        if os.path.isfile(path):
            subprocess.Popen(
                [path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x00000008,
            )
            launched = True
            logger.info("Launched Docker Desktop, waiting for daemon ...")
            break

    if not launched:
        return False, "Docker Desktop not found. Install or start it manually."

    deadline = time.time() + _DOCKER_START_TIMEOUT
    while time.time() < deadline:
        time.sleep(2)
        if _daemon_running():
            return True, "Docker Desktop started successfully."

    return False, f"Docker Desktop launched but daemon did not respond in {_DOCKER_START_TIMEOUT}s."


# Image management

# Check whether the sandbox image already exists locally
def _image_exists_locally() -> bool:
    """Return whether the configured sandbox image is present locally."""

    return _run(["docker", "image", "inspect", SANDBOX_IMAGE], timeout=10).returncode == 0

def _ensure_image() -> tuple[bool, str]:
    """Pull the sandbox image or build it locally as a fallback."""

    if _image_exists_locally():
        return True, "Image already exists locally."

    dockerfile = _DOCKERFILE_DIR / "Dockerfile"
    image_source = str(getattr(settings.sandbox, "image_source", "local") or "local").strip().lower()
    if image_source not in {"local", "registry", "auto"}:
        image_source = "local"

    def _build_local() -> tuple[bool, str]:
        if not dockerfile.exists():
            return False, f"Local Dockerfile not found: {dockerfile}"

        logger.info("Building %s locally from %s ...", SANDBOX_IMAGE, dockerfile)
        build = _run(["docker", "build", "-t", SANDBOX_IMAGE, str(_DOCKERFILE_DIR)], timeout=600)
        if build.returncode != 0:
            return False, f"Local build failed:\n{build.stderr.strip()[:400]}"
        return True, f"Built '{SANDBOX_IMAGE}' locally from Dockerfile."

    def _pull_registry() -> tuple[bool, str]:
        logger.info("Pulling %s from Docker Hub ...", SANDBOX_IMAGE)
        pull = _run(["docker", "pull", SANDBOX_IMAGE], timeout=600)
        if pull.returncode != 0:
            return False, f"Registry pull failed:\n{pull.stderr.strip()[:400]}"
        return True, f"Pulled '{SANDBOX_IMAGE}' from Docker Hub."

    if image_source == "local":
        local_ok, local_message = _build_local()
        if local_ok:
            return True, local_message

        registry_ok, registry_message = _pull_registry()
        if registry_ok:
            return True, f"{local_message}\nFallback succeeded: {registry_message}"
        return False, f"{local_message}\nRegistry fallback failed: {registry_message}"

    if image_source == "registry":
        registry_ok, registry_message = _pull_registry()
        if registry_ok:
            return True, registry_message

        local_ok, local_message = _build_local()
        if local_ok:
            return True, f"{registry_message}\nFallback succeeded: {local_message}"
        return False, f"{registry_message}\nLocal build fallback failed: {local_message}"

    registry_ok, registry_message = _pull_registry()
    if registry_ok:
        return True, registry_message

    local_ok, local_message = _build_local()
    if local_ok:
        return True, f"{registry_message}\nFallback succeeded: {local_message}"
    return False, f"{registry_message}\nLocal build fallback failed: {local_message}"


# Container lifecycle

# Check whether the named sandbox container exists
def _container_exists() -> bool:
    """Return whether the named sandbox container already exists."""

    result = _run(["docker", "ps", "-aq", "-f", f"name=^{CONTAINER_NAME}$"], timeout=10)
    return bool(result.stdout.strip())

def _container_running() -> bool:
    """Return whether the named sandbox container is currently running."""

    result = _run(["docker", "ps", "-q", "-f", f"name=^{CONTAINER_NAME}$"], timeout=10)
    return bool(result.stdout.strip())

def _start_existing() -> tuple[bool, str]:
    """Start an existing sandbox container."""

    result = _run(["docker", "start", CONTAINER_NAME], timeout=30)
    if result.returncode == 0:
        return True, f"Container '{CONTAINER_NAME}' started."
    return False, result.stderr.strip() or "Failed to start container."

def _create_and_start() -> tuple[bool, str]:
    """Create a fresh sandbox container with strict runtime limits."""

    result = _run(
        [
            "docker", "run", "-d",
            "--name", CONTAINER_NAME,
            "--restart", "unless-stopped",
            "--cpus", "1",
            "--memory", "512m",
            "--memory-swap", "512m",
            "--pids-limit", "128",
            "--network", "none",
            "--no-healthcheck",
            SANDBOX_IMAGE,
        ],
        timeout=30,
    )
    if result.returncode == 0:
        return True, f"Container '{CONTAINER_NAME}' created and started."
    return False, result.stderr.strip() or "Failed to create container."

def _ensure_running() -> tuple[bool, str]:
    """Ensure the sandbox container is running and ready for execution."""

    docker_ok, docker_msg = _ensure_docker_running()
    if not docker_ok:
        return False, docker_msg

    if _container_running():
        return True, "Container is running."

    if _container_exists():
        return _start_existing()

    image_ok, image_msg = _ensure_image()
    if not image_ok:
        return False, image_msg

    return _create_and_start()

def _restart() -> None:
    """Restart the sandbox container after a timed-out execution."""

    logger.warning("Restarting %s after timeout ...", CONTAINER_NAME)
    _run(["docker", "restart", CONTAINER_NAME], timeout=30)


# Code wrapper

# Build the Python wrapper executed inside the container
def _build_wrapper(user_code: str, auto_confirm: bool) -> str:
    """Wrap user code with UTF-8 setup and optional fake stdin support."""

    escaped = user_code.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    stdin_val = repr("y\n" * 50) if auto_confirm else "None"
    return f'''# -*- coding: utf-8 -*-
import sys, io, builtins
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

_buf = io.StringIO({stdin_val}) if {stdin_val} else None
_auto = {auto_confirm}

def _fake_input(prompt=""):
    if prompt:
        print(prompt, end="", flush=True)
    if _buf:
        line = _buf.readline()
        if line:
            return line.rstrip("\\n")
    if _auto:
        return "y"
    raise RuntimeError("stdin not available")

builtins.input = _fake_input

exec("""{escaped}""")
'''


# Public adapter

# Run Python snippets inside the managed sandbox container
class SandboxAdapter:
    """Execute bounded Python code inside the Docker sandbox."""

    def __init__(self, timeout_seconds: int | None = None, auto_confirm: bool | None = None):
        """Initialize sandbox defaults from settings when values are omitted."""

        self.timeout_seconds = timeout_seconds or settings.sandbox.timeout_seconds
        self.auto_confirm = settings.sandbox.auto_confirm if auto_confirm is None else auto_confirm

    def available(self) -> bool:
        """Return whether sandbox execution is enabled."""

        return settings.sandbox.enabled

    async def run(self, code: str, timeout_seconds: int | None = None) -> PythonExecutionResult:
        """Execute code in the sandbox and return the captured result."""

        start = time.time()

        if not self.available():
            return PythonExecutionResult(ok=False, error="Sandbox is disabled in config.", elapsed_ms=0)

        timeout = timeout_seconds or self.timeout_seconds
        ok, message = _ensure_running()
        if not ok:
            return PythonExecutionResult(
                ok=False,
                error=f"Container error: {message}",
                elapsed_ms=int((time.time() - start) * 1000),
            )

        wrapper = _build_wrapper(code, self.auto_confirm)
        cmd = [
            "docker", "exec", "-i",
            "-e", "PYTHONIOENCODING=utf-8",
            "-e", "LANG=C.UTF-8",
            CONTAINER_NAME,
            "python", "-",
        ]

        try:
            result = subprocess.run(
                cmd,
                input=wrapper,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
            )

            stdout, trunc_out = _truncate(result.stdout)
            stderr, trunc_err = _truncate(result.stderr)
            return PythonExecutionResult(
                ok=result.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                error=None if result.returncode == 0 else f"Exit code: {result.returncode}",
                elapsed_ms=int((time.time() - start) * 1000),
                truncated=trunc_out or trunc_err,
            )
        except subprocess.TimeoutExpired:
            _restart()
            return PythonExecutionResult(
                ok=False,
                error=f"Timed out after {timeout}s. Container restarted.",
                elapsed_ms=int((time.time() - start) * 1000),
            )
        except Exception as exc:
            return PythonExecutionResult(
                ok=False,
                error=f"System error: {exc}",
                elapsed_ms=int((time.time() - start) * 1000),
            )


sandbox_adapter = SandboxAdapter()
