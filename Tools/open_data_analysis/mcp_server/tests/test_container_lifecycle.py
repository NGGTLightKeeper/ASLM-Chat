"""Container lifecycle and orphan cleanup tests (no Docker required)."""
from __future__ import annotations

import os
import time
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from sandbox_mcp import runner
from sandbox_mcp.runner import (
    _cleanup_orphan_containers,
    _cleanup_run_dir,
    _container_age_seconds,
    _container_name,
    _docker_create_argv,
    _end_active_session,
    _ensure_background_cleanup_started,
    _get_active_run_dir,
    _make_run_dir,
    _session_idle_seconds,
    _touch_active_session,
)
from sandbox_mcp.files import prepare_run_layout


# ── helpers ──────────────────────────────────────────────────────────────────

def _fake_docker_factory(
    *,
    running_names: list[str] | None = None,
    labels: dict[str, dict[str, str]] | None = None,
    removed: list[str] | None = None,
):
    """Return a fake _docker callable with configurable state."""
    running = set(running_names or [])
    label_map = labels or {}

    def fake_docker(args, **kwargs):
        cmd = args[:4] if len(args) >= 4 else args

        if args[:4] == ["ps", "-a", "--filter", "label=ada.sandbox=1"]:
            payload = "\n".join(sorted(label_map.keys())) + "\n"
            return type("C", (), {"returncode": 0, "stdout": payload, "stderr": ""})()

        if args[:3] == ["inspect", "-f", "{{.State.Running}}"]:
            name = args[3]
            val = "true" if name in running else "false"
            return type("C", (), {"returncode": 0, "stdout": val + "\n", "stderr": ""})()

        if args[:3] == ["inspect", "-f", "{{json .Config.Labels}}"]:
            import json
            name = args[3]
            payload = json.dumps(label_map.get(name, {}))
            return type("C", (), {"returncode": 0, "stdout": payload, "stderr": ""})()

        if args[:2] == ["rm", "-f"]:
            name = args[2]
            if removed is not None:
                removed.append(name)
            running.discard(name)
            label_map.pop(name, None)
            return type("C", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        raise AssertionError(f"unexpected docker call: {args}")

    return fake_docker


def _container_labels(rid: str, run_dir: Path, started_at: float | None = None) -> dict[str, str]:
    labels = {
        "ada.sandbox": "1",
        "ada.sandbox.run_id": rid,
        "ada.sandbox.run_dir": str(run_dir),
    }
    if started_at is not None:
        labels["ada.sandbox.started_at"] = str(int(started_at))
    return labels


# ── started_at label ─────────────────────────────────────────────────────────

def test_docker_create_argv_includes_started_at_label(bridge_dirs, tmp_path):
    run_dir = tmp_path / ("a" * 32)
    prepare_run_layout(run_dir)

    argv = _docker_create_argv(
        container_name="sandbox-test",
        image="sandbox:latest",
        run_dir=run_dir,
    )
    assert "ada.sandbox.started_at" in " ".join(argv)
    # The label is passed as "ada.sandbox.started_at=<ts>" via --label.
    label_arg = next(a for a in argv if a.startswith("ada.sandbox.started_at="))
    ts = int(label_arg.split("=", 1)[1])
    assert abs(ts - int(time.time())) < 10


def test_container_age_seconds_parses_started_at_label(monkeypatch, tmp_path):
    rid = "c" * 32
    name = f"sandbox-{rid}"
    started_at = time.time() - 200

    monkeypatch.setattr(
        "sandbox_mcp.runner._docker",
        _fake_docker_factory(
            labels={name: _container_labels(rid, tmp_path, started_at=started_at)},
        ),
    )

    age = _container_age_seconds(name, time.time())
    assert age is not None
    assert abs(age - 200) < 5


def test_container_age_seconds_returns_none_without_label(monkeypatch, tmp_path):
    rid = "d" * 32
    name = f"sandbox-{rid}"

    monkeypatch.setattr(
        "sandbox_mcp.runner._docker",
        _fake_docker_factory(
            labels={name: _container_labels(rid, tmp_path)},  # no started_at
        ),
    )

    age = _container_age_seconds(name, time.time())
    assert age is None


# ── touch_active_session updates run_dir mtime ───────────────────────────────

def test_touch_active_session_updates_run_dir_mtime(bridge_dirs, tmp_path):
    run_dir = tmp_path / ("e" * 32)
    run_dir.mkdir()

    # Wind mtime back 10 seconds.
    old_time = time.time() - 10
    os.utime(run_dir, (old_time, old_time))
    mtime_before = run_dir.stat().st_mtime

    with runner._SESSION_LOCK:
        runner._ACTIVE_RUN_ID = run_dir.name
        runner._ACTIVE_RUN_DIR = run_dir
        runner._LAST_ACTIVITY = time.time()

    _touch_active_session()

    mtime_after = run_dir.stat().st_mtime
    assert mtime_after > mtime_before


# ── orphan cleanup: stopped containers ───────────────────────────────────────

def test_cleanup_removes_stopped_container_immediately(monkeypatch, tmp_path):
    rid = "f" * 32
    name = f"sandbox-{rid}"
    removed: list[str] = []
    run_dir = tmp_path / rid
    run_dir.mkdir()

    monkeypatch.setattr(
        "sandbox_mcp.runner._docker",
        _fake_docker_factory(
            running_names=[],           # container is stopped
            labels={name: _container_labels(rid, run_dir)},
            removed=removed,
        ),
    )
    with runner._SESSION_LOCK:
        runner._ACTIVE_RUN_ID = None

    count = _cleanup_orphan_containers()

    assert count == 1
    assert name in removed


# ── orphan cleanup: missing run_dir ──────────────────────────────────────────

def test_cleanup_removes_running_container_with_missing_run_dir(monkeypatch, tmp_path):
    rid = "1" * 32
    name = f"sandbox-{rid}"
    removed: list[str] = []
    missing_dir = tmp_path / "does_not_exist" / rid

    monkeypatch.setattr(
        "sandbox_mcp.runner._docker",
        _fake_docker_factory(
            running_names=[name],
            labels={name: _container_labels(rid, missing_dir, started_at=time.time() - 5)},
            removed=removed,
        ),
    )
    with runner._SESSION_LOCK:
        runner._ACTIVE_RUN_ID = None

    count = _cleanup_orphan_containers()

    assert count == 1
    assert name in removed


# ── orphan cleanup: stale mtime + stale started_at ───────────────────────────

def test_cleanup_removes_running_container_when_both_mtime_and_age_stale(
    monkeypatch, tmp_path
):
    rid = "2" * 32
    name = f"sandbox-{rid}"
    removed: list[str] = []
    run_dir = tmp_path / rid
    run_dir.mkdir()

    idle = _session_idle_seconds()
    # Both mtime and started_at are older than idle timeout.
    stale_time = time.time() - idle - 60
    os.utime(run_dir, (stale_time, stale_time))

    monkeypatch.setattr(
        "sandbox_mcp.runner._docker",
        _fake_docker_factory(
            running_names=[name],
            labels={name: _container_labels(rid, run_dir, started_at=stale_time)},
            removed=removed,
        ),
    )
    with runner._SESSION_LOCK:
        runner._ACTIVE_RUN_ID = None

    count = _cleanup_orphan_containers()

    assert count == 1
    assert name in removed


# ── orphan cleanup: fresh mtime must NOT be removed ──────────────────────────

def test_cleanup_keeps_running_container_with_fresh_mtime(monkeypatch, tmp_path):
    rid = "3" * 32
    name = f"sandbox-{rid}"
    removed: list[str] = []
    run_dir = tmp_path / rid
    run_dir.mkdir()

    # Both mtime and started_at are fresh.
    now = time.time()
    os.utime(run_dir, (now, now))

    monkeypatch.setattr(
        "sandbox_mcp.runner._docker",
        _fake_docker_factory(
            running_names=[name],
            labels={name: _container_labels(rid, run_dir, started_at=now - 5)},
            removed=removed,
        ),
    )
    with runner._SESSION_LOCK:
        runner._ACTIVE_RUN_ID = None

    count = _cleanup_orphan_containers()

    assert count == 0
    assert removed == []


# ── orphan cleanup: stale mtime but fresh started_at is kept ────────────────

def test_cleanup_keeps_container_with_stale_mtime_but_fresh_started_at(
    monkeypatch, tmp_path
):
    """If started_at is recent the container is still treated as alive.
    This prevents killing a freshly created container whose run_dir was not touched yet."""
    rid = "4" * 32
    name = f"sandbox-{rid}"
    removed: list[str] = []
    run_dir = tmp_path / rid
    run_dir.mkdir()

    idle = _session_idle_seconds()
    stale_time = time.time() - idle - 60
    os.utime(run_dir, (stale_time, stale_time))  # mtime stale

    monkeypatch.setattr(
        "sandbox_mcp.runner._docker",
        _fake_docker_factory(
            running_names=[name],
            labels={name: _container_labels(rid, run_dir, started_at=time.time() - 5)},  # age fresh
            removed=removed,
        ),
    )
    with runner._SESSION_LOCK:
        runner._ACTIVE_RUN_ID = None

    count = _cleanup_orphan_containers()

    assert count == 0
    assert removed == []


# ── active session is never evicted ──────────────────────────────────────────

def test_cleanup_skips_active_session_container(monkeypatch, tmp_path):
    rid = "5" * 32
    name = f"sandbox-{rid}"
    removed: list[str] = []
    run_dir = tmp_path / rid
    run_dir.mkdir()

    idle = _session_idle_seconds()
    stale_time = time.time() - idle - 60
    os.utime(run_dir, (stale_time, stale_time))

    monkeypatch.setattr(
        "sandbox_mcp.runner._docker",
        _fake_docker_factory(
            running_names=[name],
            labels={name: _container_labels(rid, run_dir, started_at=stale_time)},
            removed=removed,
        ),
    )
    # Mark rid as the active session of THIS process.
    with runner._SESSION_LOCK:
        runner._ACTIVE_RUN_ID = rid

    count = _cleanup_orphan_containers()

    assert count == 0
    assert removed == []


# ── bogus run_id is removed immediately ──────────────────────────────────────

def test_cleanup_removes_container_with_bogus_run_id(monkeypatch, tmp_path):
    name = "sandbox-not-a-uuid"
    removed: list[str] = []

    monkeypatch.setattr(
        "sandbox_mcp.runner._docker",
        _fake_docker_factory(
            running_names=[name],
            labels={name: {"ada.sandbox": "1", "ada.sandbox.run_id": "not-a-uuid"}},
            removed=removed,
        ),
    )
    with runner._SESSION_LOCK:
        runner._ACTIVE_RUN_ID = None

    count = _cleanup_orphan_containers()

    assert count == 1
    assert name in removed


# ── background reaper starts once ────────────────────────────────────────────

def test_ensure_background_cleanup_started_is_idempotent(monkeypatch):
    # Patch so we don't spin a real thread.
    started: list[dict] = []

    class FakeThread:
        def __init__(self, target, args, name, daemon):
            started.append({"name": name, "daemon": daemon})

        def start(self):
            pass

    monkeypatch.setattr(runner, "_BACKGROUND_CLEANUP_STARTED", False)
    monkeypatch.setattr("sandbox_mcp.runner.threading.Thread", FakeThread)

    _ensure_background_cleanup_started()
    _ensure_background_cleanup_started()
    _ensure_background_cleanup_started()

    assert len(started) == 1
    assert started[0]["name"] == "oda-sandbox-reaper"
    assert started[0]["daemon"] is True

    monkeypatch.setattr(runner, "_BACKGROUND_CLEANUP_STARTED", False)


# ── multi-container scenario: only stale orphan removed ──────────────────────

def test_cleanup_only_removes_stale_not_fresh_in_mixed_set(monkeypatch, tmp_path):
    """Two containers coexist: one stale (should go), one fresh (must stay)."""
    idle = _session_idle_seconds()
    now = time.time()

    rid_fresh = "6" * 32
    rid_stale = "7" * 32
    name_fresh = f"sandbox-{rid_fresh}"
    name_stale = f"sandbox-{rid_stale}"

    dir_fresh = tmp_path / rid_fresh
    dir_fresh.mkdir()
    os.utime(dir_fresh, (now, now))

    dir_stale = tmp_path / rid_stale
    dir_stale.mkdir()
    stale_time = now - idle - 120
    os.utime(dir_stale, (stale_time, stale_time))

    removed: list[str] = []
    labels = {
        name_fresh: _container_labels(rid_fresh, dir_fresh, started_at=now - 10),
        name_stale: _container_labels(rid_stale, dir_stale, started_at=stale_time),
    }

    monkeypatch.setattr(
        "sandbox_mcp.runner._docker",
        _fake_docker_factory(
            running_names=[name_fresh, name_stale],
            labels=labels,
            removed=removed,
        ),
    )
    with runner._SESSION_LOCK:
        runner._ACTIVE_RUN_ID = None

    count = _cleanup_orphan_containers()

    assert count == 1
    assert name_stale in removed
    assert name_fresh not in removed


# ── atexit handler does not raise ─────────────────────────────────────────────

def test_cleanup_active_session_at_exit_is_safe(bridge_dirs):
    """atexit handler must not propagate exceptions."""
    original = runner._end_active_session
    runner._end_active_session = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        from sandbox_mcp.runner import _cleanup_active_session_at_exit
        _cleanup_active_session_at_exit()  # must not raise
    finally:
        runner._end_active_session = original


# ── _cleanup_run_dir removes the container by name ───────────────────────────

def test_cleanup_run_dir_removes_associated_container(monkeypatch, tmp_path, bridge_dirs):
    rid = "8" * 32
    run_dir = tmp_path / rid
    run_dir.mkdir()
    removed: list[str] = []

    def fake_docker(args, **kwargs):
        if args[:2] == ["rm", "-f"]:
            removed.append(args[2])
        return type("C", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("sandbox_mcp.runner._docker", fake_docker)
    monkeypatch.setattr("sandbox_mcp.runner.send_to_trash", lambda _: None)
    monkeypatch.delenv("SANDBOX_ARCHIVE_RUNS", raising=False)

    _cleanup_run_dir(run_dir)

    assert _container_name(rid) in removed
