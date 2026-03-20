# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import secrets
import threading
from datetime import datetime, timedelta

from sandbox.config import TOKEN_TTL_SECONDS

_token_registry: dict[str, dict] = {}
_registry_lock = threading.Lock()
_cleanup_thread: threading.Thread | None = None
_cleanup_stop_event = threading.Event()


# Token registration.

def _generate_token() -> str:
    """Create a random share token."""

    return secrets.token_urlsafe(16)


# Token storage.

def _register_token(path: str, token_type: str = "file") -> str:
    """Store a token entry for a shared path."""

    token = _generate_token()
    expires = datetime.now() + timedelta(seconds=TOKEN_TTL_SECONDS)

    with _registry_lock:
        _token_registry[token] = {
            "path": path,
            "type": token_type,
            "expires": expires,
        }

    return token


def _get_token_info(token: str) -> dict | None:
    """Return token metadata when it is still valid."""

    with _registry_lock:
        info = _token_registry.get(token)
        if info and info["expires"] > datetime.now():
            return info

        if info:
            del _token_registry[token]

    return None


def _cleanup_expired_tokens() -> None:
    """Remove expired token entries."""

    now = datetime.now()

    with _registry_lock:
        expired_tokens = [
            token
            for token, info in _token_registry.items()
            if info["expires"] <= now
        ]

        for token in expired_tokens:
            del _token_registry[token]


# Background cleanup.

def _start_token_cleanup(interval_seconds: int | None = None) -> None:
    """Start the expired-token cleanup thread."""

    global _cleanup_thread

    if _cleanup_thread and _cleanup_thread.is_alive():
        return

    interval = interval_seconds or max(60, TOKEN_TTL_SECONDS // 2)
    _cleanup_stop_event.clear()

    def _run() -> None:
        while not _cleanup_stop_event.wait(interval):
            _cleanup_expired_tokens()

    _cleanup_thread = threading.Thread(
        target=_run,
        name="token-cleanup",
        daemon=True,
    )
    _cleanup_thread.start()


def _stop_token_cleanup() -> None:
    """Stop the expired-token cleanup thread."""

    global _cleanup_thread

    if not _cleanup_thread:
        return

    _cleanup_stop_event.set()
    _cleanup_thread.join(timeout=5)
    _cleanup_thread = None
