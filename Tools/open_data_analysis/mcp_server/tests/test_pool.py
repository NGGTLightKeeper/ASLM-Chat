"""Unit tests for container_pool (no Docker required)."""
from __future__ import annotations

import json
import time
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from sandbox_mcp import container_pool
from sandbox_mcp.container_pool import (
    _container_name,
    _sanitize_scope,
    _scope_dir,
    _PoolEntry,
    _POOL,
    _POOL_LOCK,
    _janitor_once,
    acquire,
    evict,
    pool_status,
    evict_legacy_sandbox_containers,
    DockerNotFoundError,
    PoolError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_docker_factory(
    *,
    running: set[str] | None = None,
    label_map: dict[str, dict[str, str]] | None = None,
    removed: list[str] | None = None,
    image_ok: bool = True,
):
    """Return a fake _docker callable."""
    _running = set(running or [])
    _labels = dict(label_map or {})

    def fake(args, **kwargs):
        # image inspect
        if args[:2] == ["image", "inspect"]:
            if not image_ok:
                return _r(1, "", "no such image")
            data = [{"Config": {"Labels": {"org.aslm.oda.sandbox-runtime": "container-v1"}}}]
            return _r(0, json.dumps(data), "")

        # container running
        if args[:3] == ["inspect", "-f", "{{.State.Running}}"]:
            name = args[3]
            val = "true" if name in _running else "false"
            return _r(0, val + "\n", "")

        # labels
        if args[:3] == ["inspect", "-f", "{{json .Config.Labels}}"]:
            name = args[3]
            return _r(0, json.dumps(_labels.get(name, {})), "")

        # docker run (create)
        if args[0] == "run":
            name_idx = args.index("--name") + 1 if "--name" in args else None
            name = args[name_idx] if name_idx else "unknown"
            _running.add(name)
            _labels[name] = {
                "ada.pool": "1",
                "ada.pool.scope": name.replace("oda-chat-", ""),
                "ada.pool.last_used": str(int(time.time())),
            }
            return _r(0, name, "")

        # docker rm
        if args[:2] == ["rm", "-f"]:
            name = args[2]
            _running.discard(name)
            _labels.pop(name, None)
            if removed is not None:
                removed.append(name)
            return _r(0, "", "")

        # docker exec (health check or supervisor)
        if args[0] == "exec":
            return _r(0, "ok", "")

        # docker ps
        if args[:2] == ["ps", "-a"]:
            payload = "\n".join(sorted(_labels.keys())) + "\n"
            return _r(0, payload, "")

        raise AssertionError(f"unexpected docker call: {args}")

    return fake


def _r(returncode, stdout, stderr):
    import subprocess
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture(autouse=True)
def clean_pool(tmp_path, monkeypatch):
    """Reset pool state before/after each test."""
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "oda-sandbox"))
    monkeypatch.setenv("SANDBOX_SHARED_ROOT", str(tmp_path / "_sandbox"))
    monkeypatch.setenv("SANDBOX_POOL_ROOT", str(tmp_path / "pool"))
    (tmp_path / "_sandbox").mkdir(parents=True, exist_ok=True)
    with _POOL_LOCK:
        _POOL.clear()
    yield
    with _POOL_LOCK:
        _POOL.clear()


# ---------------------------------------------------------------------------
# Scope / name helpers
# ---------------------------------------------------------------------------

def test_sanitize_scope_strips_special_chars():
    assert _sanitize_scope("Chat-123") == "chat-123"
    assert _sanitize_scope("abc/def") == "abc-def"
    assert _sanitize_scope("") == "default"
    long_scope = "a" * 100
    assert len(_sanitize_scope(long_scope)) == 60


def test_container_name_format():
    assert _container_name("chat-abc") == "oda-chat-chat-abc"
    # Trailing special chars are stripped by _sanitize_scope
    assert _container_name("Chat ABC!") == "oda-chat-chat-abc"


# ---------------------------------------------------------------------------
# acquire: reuse existing healthy container
# ---------------------------------------------------------------------------

def test_acquire_reuses_same_container(monkeypatch, tmp_path):
    name = _container_name("chat-a")
    fake = _fake_docker_factory(running={name})
    monkeypatch.setattr(container_pool, "_docker", fake)

    c1 = acquire("chat-a")
    c2 = acquire("chat-a")

    assert c1 == c2 == name


def test_acquire_creates_container_when_absent(monkeypatch, tmp_path):
    removed: list[str] = []
    fake = _fake_docker_factory(removed=removed)
    monkeypatch.setattr(container_pool, "_docker", fake)

    name = acquire("chat-new")
    assert name == _container_name("chat-new")


def test_acquire_different_scopes_get_different_containers(monkeypatch, tmp_path):
    fake = _fake_docker_factory()
    monkeypatch.setattr(container_pool, "_docker", fake)

    a = acquire("chat-a")
    b = acquire("chat-b")

    assert a != b
    assert "chat-a" in a
    assert "chat-b" in b


def test_acquire_recreates_unhealthy_container(monkeypatch, tmp_path):
    name = _container_name("chat-sick")
    removed: list[str] = []

    def fake(args, **kwargs):
        if args[:2] == ["image", "inspect"]:
            data = [{"Config": {"Labels": {"org.aslm.oda.sandbox-runtime": "container-v1"}}}]
            return _r(0, json.dumps(data), "")
        if args[:3] == ["inspect", "-f", "{{.State.Running}}"]:
            return _r(0, "true\n", "")
        if args[:3] == ["inspect", "-f", "{{json .Config.Labels}}"]:
            return _r(0, json.dumps({"ada.pool": "1"}), "")
        if args[0] == "exec":
            # Health check fails first time, succeeds after recreate
            if args[1] != "-u":
                return _r(1, "bad:uid", "")
            return _r(1, "bad:uid", "")
        if args[:2] == ["rm", "-f"]:
            removed.append(args[2])
            return _r(0, "", "")
        if args[0] == "run":
            return _r(0, name, "")
        raise AssertionError(f"unexpected: {args}")

    # Seed pool with a "healthy"-looking entry so acquire checks health first
    with _POOL_LOCK:
        _POOL[_sanitize_scope("chat-sick")] = _PoolEntry(
            container_name=name, scope="chat-sick"
        )

    monkeypatch.setattr(container_pool, "_docker", fake)

    with pytest.raises(PoolError):
        # Will fail because recreated container also fails health
        acquire("chat-sick")
    assert name in removed


def test_acquire_raises_pool_error_on_bad_image(monkeypatch, tmp_path):
    fake = _fake_docker_factory(image_ok=False)
    monkeypatch.setattr(container_pool, "_docker", fake)

    with pytest.raises(PoolError, match="image not found"):
        acquire("chat-bad-image")


# ---------------------------------------------------------------------------
# exec_in_pool: timeout does NOT remove container
# ---------------------------------------------------------------------------

def test_exec_timeout_does_not_remove_container(monkeypatch, tmp_path):
    """On outer timeout the container must survive."""
    name = _container_name("chat-timeout")
    removed: list[str] = []

    # Seed pool with healthy container
    with _POOL_LOCK:
        _POOL[_sanitize_scope("chat-timeout")] = _PoolEntry(
            container_name=name, scope="chat-timeout"
        )

    fake = _fake_docker_factory(running={name}, removed=removed)
    monkeypatch.setattr(container_pool, "_docker", fake)

    import subprocess

    def fake_subprocess_run(args, **kwargs):
        if "exec" in args:
            raise subprocess.TimeoutExpired(args, kwargs.get("timeout", 0))
        return fake(args[1:], **kwargs)

    monkeypatch.setattr(container_pool.subprocess, "run", fake_subprocess_run)

    exit_code, stdout, stderr, timed_out = container_pool.exec_in_pool(
        "chat-timeout", ["python3", "-c", "import time; time.sleep(9999)"], timeout_s=1
    )

    assert timed_out is True
    assert exit_code == 124
    # Container must still be in pool, not removed
    assert removed == []
    with _POOL_LOCK:
        assert _sanitize_scope("chat-timeout") in _POOL


# ---------------------------------------------------------------------------
# evict
# ---------------------------------------------------------------------------

def test_evict_removes_container(monkeypatch, tmp_path):
    name = _container_name("chat-evict")
    removed: list[str] = []
    fake = _fake_docker_factory(running={name}, removed=removed)
    monkeypatch.setattr(container_pool, "_docker", fake)

    with _POOL_LOCK:
        _POOL[_sanitize_scope("chat-evict")] = _PoolEntry(
            container_name=name, scope="chat-evict"
        )

    result = evict("chat-evict")

    assert result is True
    assert name in removed
    with _POOL_LOCK:
        assert _sanitize_scope("chat-evict") not in _POOL


def test_evict_nonexistent_scope_returns_false(monkeypatch, tmp_path):
    fake = _fake_docker_factory()
    monkeypatch.setattr(container_pool, "_docker", fake)

    result = evict("chat-nonexistent")
    assert result is False


# ---------------------------------------------------------------------------
# pool_status
# ---------------------------------------------------------------------------

def test_pool_status_reflects_entries(monkeypatch, tmp_path):
    name_a = _container_name("chat-status-a")
    name_b = _container_name("chat-status-b")

    fake = _fake_docker_factory(running={name_a, name_b})
    monkeypatch.setattr(container_pool, "_docker", fake)

    with _POOL_LOCK:
        _POOL[_sanitize_scope("chat-status-a")] = _PoolEntry(name_a, "chat-status-a")
        _POOL[_sanitize_scope("chat-status-b")] = _PoolEntry(name_b, "chat-status-b")

    status = pool_status()
    scopes = {s["scope"] for s in status}
    assert "chat-status-a" in scopes
    assert "chat-status-b" in scopes


# ---------------------------------------------------------------------------
# Janitor: idle eviction
# ---------------------------------------------------------------------------

def test_janitor_evicts_idle_container(monkeypatch, tmp_path):
    # min_v for SANDBOX_POOL_IDLE_SECONDS is 60; use 120 and stale_age 200.
    monkeypatch.setenv("SANDBOX_POOL_IDLE_SECONDS", "120")
    name = _container_name("chat-idle")
    removed: list[str] = []
    fake = _fake_docker_factory(running={name}, removed=removed)
    monkeypatch.setattr(container_pool, "_docker", fake)

    old_ts = time.time() - 200   # 200s old, idle=120 → stale
    with _POOL_LOCK:
        entry = _PoolEntry(container_name=name, scope="chat-idle")
        entry.last_used = old_ts
        _POOL[_sanitize_scope("chat-idle")] = entry

    _janitor_once()

    assert name in removed
    with _POOL_LOCK:
        assert _sanitize_scope("chat-idle") not in _POOL


def test_janitor_keeps_fresh_container(monkeypatch, tmp_path):
    monkeypatch.setenv("SANDBOX_POOL_IDLE_SECONDS", "3600")
    name = _container_name("chat-fresh")
    removed: list[str] = []
    fake = _fake_docker_factory(running={name}, removed=removed)
    monkeypatch.setattr(container_pool, "_docker", fake)

    with _POOL_LOCK:
        _POOL[_sanitize_scope("chat-fresh")] = _PoolEntry(name, "chat-fresh")

    _janitor_once()

    assert name not in removed
    with _POOL_LOCK:
        assert _sanitize_scope("chat-fresh") in _POOL


# ---------------------------------------------------------------------------
# Legacy container migration
# ---------------------------------------------------------------------------

def test_evict_legacy_sandbox_containers(monkeypatch, tmp_path):
    removed: list[str] = []

    def fake(args, **kwargs):
        if args[:4] == ["ps", "-a", "--filter", "label=ada.sandbox=1"]:
            return _r(0, "sandbox-abc123\nsandbox-def456\n", "")
        if args[:2] == ["rm", "-f"]:
            removed.append(args[2])
            return _r(0, "", "")
        raise AssertionError(f"unexpected: {args}")

    monkeypatch.setattr(container_pool, "_docker", fake)

    count = evict_legacy_sandbox_containers()

    assert count == 2
    assert "sandbox-abc123" in removed
    assert "sandbox-def456" in removed


# ---------------------------------------------------------------------------
# start_janitor idempotency
# ---------------------------------------------------------------------------

def test_start_janitor_idempotent(monkeypatch):
    import sandbox_mcp.container_pool as cp
    monkeypatch.setattr(cp, "_JANITOR_STARTED", False)
    started_threads: list[str] = []

    class FakeThread:
        def __init__(self, *, target, args, name, daemon):
            started_threads.append(name)

        def start(self):
            pass

    monkeypatch.setattr(cp.threading, "Thread", FakeThread)

    cp.start_janitor(interval_seconds=9999)
    cp.start_janitor(interval_seconds=9999)
    cp.start_janitor(interval_seconds=9999)

    assert len(started_threads) == 1
    assert started_threads[0] == "oda-pool-janitor"
    monkeypatch.setattr(cp, "_JANITOR_STARTED", False)
