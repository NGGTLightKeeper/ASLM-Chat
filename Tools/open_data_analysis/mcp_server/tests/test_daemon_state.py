"""Tests for daemon state persistence (pool format)."""
from __future__ import annotations

import json
import logging
import time

import pytest

from sandbox_mcp import daemon, container_pool
from sandbox_mcp.container_pool import _POOL, _POOL_LOCK


@pytest.fixture(autouse=True)
def clear_pool():
    with _POOL_LOCK:
        _POOL.clear()
    yield
    with _POOL_LOCK:
        _POOL.clear()


def test_restore_state_ignores_invalid_json(monkeypatch, tmp_path, caplog):
    """Unreadable state file is silently discarded (warning only, no quarantine)."""
    state = tmp_path / "state.json"
    state.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("SANDBOX_STATE_PATH", str(state))

    with caplog.at_level(logging.WARNING):
        daemon._restore_state()

    # File may survive (new daemon just warns and ignores)
    assert "unreadable" in caplog.text or "malformed" in caplog.text or "state file" in caplog.text
    with _POOL_LOCK:
        assert len(_POOL) == 0


def test_restore_state_ignores_missing_scopes_key(monkeypatch, tmp_path):
    """State without 'scopes' key is silently ignored."""
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"legacy_key": "value"}), encoding="utf-8")
    monkeypatch.setenv("SANDBOX_STATE_PATH", str(state))

    daemon._restore_state()

    with _POOL_LOCK:
        assert len(_POOL) == 0


def test_restore_state_skips_missing_container(monkeypatch, tmp_path):
    """Containers that are no longer running are skipped during restore."""
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps({
            "scopes": {
                "chat-abc": {
                    "scope": "chat-abc",
                    "container": "oda-chat-chat-abc",
                    "last_used": time.time() - 5,
                }
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("SANDBOX_STATE_PATH", str(state))

    def fake_docker(args, **kwargs):
        if args[:3] == ["inspect", "-f", "{{.State.Running}}"]:
            return _r(0, "false\n", "")
        return _r(0, "", "")

    monkeypatch.setattr(container_pool, "_docker", fake_docker)

    daemon._restore_state()

    with _POOL_LOCK:
        assert "chat-abc" not in _POOL


def test_restore_state_reattaches_healthy_container(monkeypatch, tmp_path):
    """Containers that are still running and healthy are reattached."""
    state = tmp_path / "state.json"
    now = time.time()
    state.write_text(
        json.dumps({
            "scopes": {
                "chat-xyz": {
                    "scope": "chat-xyz",
                    "container": "oda-chat-chat-xyz",
                    "last_used": now - 5,
                }
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("SANDBOX_STATE_PATH", str(state))

    def fake_docker(args, **kwargs):
        if args[:3] == ["inspect", "-f", "{{.State.Running}}"]:
            return _r(0, "true\n", "")
        if args[0] == "exec":
            return _r(0, "ok", "")
        return _r(0, "", "")

    monkeypatch.setattr(container_pool, "_docker", fake_docker)
    monkeypatch.setenv("SANDBOX_SHARED_ROOT", str(tmp_path / "_sandbox"))
    (tmp_path / "_sandbox").mkdir(parents=True, exist_ok=True)

    daemon._restore_state()

    with _POOL_LOCK:
        assert "chat-xyz" in _POOL
        assert _POOL["chat-xyz"].container_name == "oda-chat-chat-xyz"


def _r(returncode, stdout, stderr):
    import subprocess
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)
