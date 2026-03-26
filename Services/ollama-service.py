# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from Settings import settings

logger = logging.getLogger(__name__)

_ollama_process: subprocess.Popen | None = None
PID_FILE = Path(__file__).resolve().parent.parent / "Settings" / "ollama-service.pid"


# Read saved service PID
def _read_pid() -> int | None:
    """Return the saved Ollama PID when it exists."""

    try:
        raw_value = PID_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    if not raw_value:
        return None

    try:
        return int(raw_value)
    except ValueError:
        return None

# Save service PID
def _write_pid(pid: int) -> None:
    """Persist the managed Ollama PID on disk."""

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid), encoding="utf-8")

# Delete saved service PID
def _clear_pid() -> None:
    """Remove the saved Ollama PID file."""

    try:
        PID_FILE.unlink()
    except OSError:
        pass


# Check saved process state
def _is_pid_running(pid: int | None) -> bool:
    """Return whether the given PID still points to a live process."""

    if not pid:
        return False

    try:
        os.kill(pid, 0)
    except (OSError, SystemError):
        return False

    return True

# Wait for HTTP readiness
def _wait_until_ready(timeout_seconds: float = 15.0) -> bool:
    """Wait until the local Ollama HTTP endpoint starts responding."""

    deadline = time.time() + timeout_seconds
    host = settings.get_engine_url("ollama-service")
    version_url = f"{host.rstrip('/')}/api/version"

    while time.time() < deadline:
        try:
            with urlopen(version_url, timeout=1.5) as response:
                if response.status < 500:
                    return True
        except (OSError, URLError):
            time.sleep(0.25)

    return False


# Start managed service
def start_ollama() -> None:
    """Start the local Ollama service when the active engine requires it."""

    global _ollama_process

    # Skip startup when the current runtime does not use the managed Ollama
    # service or when it is disabled in settings.
    active_engine = settings.get_llm_engine()
    if not settings.is_ollama_engine(active_engine) or not settings.get("ollama-service", False):
        return

    # Reuse an already running process tracked on disk.
    tracked_pid = _read_pid()
    if tracked_pid and _is_pid_running(tracked_pid):
        logger.info("Ollama service is already running (PID: %s)", tracked_pid)
        return

    # Validate the configured executable before attempting to spawn it.
    ollama_path = settings.get("ollama-service_path")
    if not ollama_path or not os.path.exists(ollama_path):
        print(f"[ASLM-Chat] Ollama service is enabled but not found at: {ollama_path}")
        return

    ollama_models = settings.get("ollama-service_models")
    ollama_port = settings.get("ollama-service_port", 30002)

    # The managed service uses environment variables for its bind address and
    # optional custom model directory.
    env = os.environ.copy()
    env["OLLAMA_HOST"] = f"127.0.0.1:{ollama_port}"
    if ollama_models:
        env["OLLAMA_MODELS"] = str(ollama_models)

    print(f"[ASLM-Chat] Starting local Ollama service on port {ollama_port}...")

    try:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        _ollama_process = subprocess.Popen(
            [ollama_path, "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )

        _write_pid(_ollama_process.pid)

        if not _wait_until_ready():
            logger.warning("Ollama process started but the HTTP endpoint did not become ready in time.")

        print(f"[ASLM-Chat] Ollama service started successfully (PID: {_ollama_process.pid})")
    except Exception as exc:
        _ollama_process = None
        _clear_pid()
        print(f"[ASLM-Chat] Failed to start Ollama service: {exc}")


# Stop managed service
def stop_ollama() -> None:
    """Stop the managed Ollama service when a tracked PID exists."""

    global _ollama_process

    pid = _read_pid()
    if not pid:
        _ollama_process = None
        return

    try:
        # Windows needs ``taskkill`` to terminate the full spawned tree, while
        # POSIX systems can stop the recorded PID directly.
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError:
        logger.info("Managed Ollama process %s was already stopped.", pid)
    finally:
        _ollama_process = None
        _clear_pid()
