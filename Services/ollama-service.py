"""Process helpers for the local Ollama background service."""

from __future__ import annotations

import logging
import os
import subprocess

from Settings import settings

logger = logging.getLogger(__name__)

# Keep a process reference for the current Python runtime.
_ollama_process: subprocess.Popen | None = None


def start_ollama() -> None:
    """Start the local Ollama service when the active engine requires it."""
    global _ollama_process

    active_engine = settings.get_llm_engine()
    if not settings.is_ollama_engine(active_engine) or not settings.get("ollama-service", False):
        return

    if _ollama_process is not None and _ollama_process.poll() is None:
        logger.info("Ollama service is already running (PID: %s)", _ollama_process.pid)
        return

    ollama_path = settings.get("ollama-service_path")
    if not ollama_path or not os.path.exists(ollama_path):
        print(f"[ASLM-Chat] Ollama service is enabled but not found at: {ollama_path}")
        return

    ollama_models = settings.get("ollama-service_models")
    ollama_port = settings.get("ollama-service_port", 30002)

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
        print(f"[ASLM-Chat] Ollama service started successfully (PID: {_ollama_process.pid})")
    except Exception as exc:
        _ollama_process = None
        print(f"[ASLM-Chat] Failed to start Ollama service: {exc}")
