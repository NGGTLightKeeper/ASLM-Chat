# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from sandbox.config import (
    WORKSPACE_CLEANUP_ENABLED,
    WORKSPACE_CLEANUP_IDLE_SECONDS,
    WORKSPACE_CLEANUP_INTERVAL_SECONDS,
    WORKSPACE_CLEANUP_RECYCLE_SECONDS,
)
from sandbox.workspace import task_root

TMP_DIR_NAME = "tmp"
BATCH_PREFIX = "idle-"
BATCH_METADATA = ".sandbox_cleanup_batch.json"
STATE_FILENAME = ".sandbox_cleanup_state.json"
_RESERVED_ROOT_NAMES = {TMP_DIR_NAME, STATE_FILENAME}

_LOCK = threading.RLock()
_MONITOR_STARTED = False
_ACTIVE_CALLS = 0
_LAST_ACTIVITY_MONOTONIC = time.monotonic()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _parse_iso_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _safe_batch_name() -> str:
    return BATCH_PREFIX + _utc_now().strftime("%Y%m%d-%H%M%S")


def _unique_child(parent: Path, name: str) -> Path:
    candidate = parent / name
    if not candidate.exists():
        return candidate
    for index in range(2, 1000):
        candidate = parent / f"{name}-{index}"
        if not candidate.exists():
            return candidate
    return parent / f"{name}-{time.time_ns()}"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _remember_cleanup_event(root: Path, event: str, **details: object) -> None:
    try:
        _write_json(
            root / STATE_FILENAME,
            {
                "event": event,
                "updated_at": _iso_now(),
                **details,
            },
        )
    except OSError:
        pass


def _iter_stageable_root_entries(root: Path) -> list[Path]:
    try:
        entries = list(root.iterdir())
    except OSError:
        return []
    return [
        entry
        for entry in entries
        if entry.name not in _RESERVED_ROOT_NAMES
    ]


def stage_workspace_to_tmp(staged_at: datetime | None = None) -> Path | None:
    """Move current root entries into one tmp batch inside the sandbox."""

    root = task_root()
    root.mkdir(parents=True, exist_ok=True)
    entries = _iter_stageable_root_entries(root)
    if not entries:
        return None

    tmp_root = root / TMP_DIR_NAME
    tmp_root.mkdir(parents=True, exist_ok=True)
    batch_dir = _unique_child(tmp_root, _safe_batch_name())
    batch_dir.mkdir(parents=True, exist_ok=False)

    moved: list[str] = []
    for entry in entries:
        if not entry.exists():
            continue
        destination = batch_dir / entry.name
        try:
            shutil.move(str(entry), str(destination))
            moved.append(entry.name)
        except (OSError, shutil.Error):
            continue

    if not moved:
        with contextlib.suppress(OSError):
            batch_dir.rmdir()
        return None

    staged_at = staged_at or _utc_now()
    metadata = {
        "staged_at": staged_at.isoformat(),
        "source": str(root),
        "moved_entries": moved,
    }
    with contextlib.suppress(OSError):
        _write_json(batch_dir / BATCH_METADATA, metadata)
    _remember_cleanup_event(
        root,
        "staged",
        batch=str(batch_dir),
        moved_count=len(moved),
    )
    return batch_dir


def _batch_staged_at(batch_dir: Path) -> datetime | None:
    metadata = _read_json(batch_dir / BATCH_METADATA)
    staged_at = _parse_iso_timestamp(metadata.get("staged_at"))
    if staged_at is not None:
        return staged_at
    try:
        return datetime.fromtimestamp(batch_dir.stat().st_mtime, timezone.utc)
    except OSError:
        return None


def _send_to_windows_recycle_bin(path: Path) -> None:
    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_uint),
            ("fAnyOperationsAborted", ctypes.c_bool),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    operation = SHFILEOPSTRUCTW()
    operation.wFunc = 3  # FO_DELETE
    operation.pFrom = str(path) + "\0\0"
    operation.fFlags = 0x40 | 0x10 | 0x04 | 0x400  # undo, no confirm, silent, no UI

    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted:
        raise OSError(f"SHFileOperationW failed with code {result}")


def _send_to_platform_trash(path: Path) -> None:
    if os.name == "nt":
        _send_to_windows_recycle_bin(path)
        return

    try:
        from send2trash import send2trash  # type: ignore
    except Exception:
        send2trash = None

    if send2trash is not None:
        send2trash(str(path))
        return

    gio = shutil.which("gio")
    if gio:
        subprocess.run([gio, "trash", str(path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return

    raise OSError("No platform trash backend is available.")


def recycle_due_tmp_batches(now: datetime | None = None) -> list[Path]:
    """Move expired tmp batches to the OS trash without depending on trash name."""

    root = task_root()
    tmp_root = root / TMP_DIR_NAME
    if not tmp_root.exists() or not tmp_root.is_dir():
        return []

    now = now or _utc_now()
    recycled: list[Path] = []
    for batch_dir in sorted(tmp_root.iterdir(), key=lambda path: path.name):
        if not batch_dir.is_dir() or not batch_dir.name.startswith(BATCH_PREFIX):
            continue
        staged_at = _batch_staged_at(batch_dir)
        if staged_at is None:
            continue
        if (now - staged_at).total_seconds() < WORKSPACE_CLEANUP_RECYCLE_SECONDS:
            continue
        try:
            _send_to_platform_trash(batch_dir)
        except OSError as exc:
            _remember_cleanup_event(
                root,
                "recycle_failed",
                batch=str(batch_dir),
                error=str(exc),
            )
            continue
        recycled.append(batch_dir)
        _remember_cleanup_event(root, "recycled", batch=str(batch_dir))

    return recycled


def run_cleanup_once() -> None:
    """Perform one cleanup pass if the sandbox is idle."""

    if not WORKSPACE_CLEANUP_ENABLED:
        return

    with _LOCK:
        now = _utc_now()
        recycle_due_tmp_batches(now=now)
        if _ACTIVE_CALLS > 0:
            return
        idle_for = time.monotonic() - _LAST_ACTIVITY_MONOTONIC
        if idle_for >= WORKSPACE_CLEANUP_IDLE_SECONDS:
            stage_workspace_to_tmp(staged_at=now)


def _monitor_loop() -> None:
    interval = max(1, WORKSPACE_CLEANUP_INTERVAL_SECONDS)
    while True:
        time.sleep(interval)
        with contextlib.suppress(Exception):
            run_cleanup_once()


def ensure_cleanup_monitor_started() -> None:
    global _MONITOR_STARTED
    if not WORKSPACE_CLEANUP_ENABLED:
        return
    with _LOCK:
        if _MONITOR_STARTED:
            return
        thread = threading.Thread(
            target=_monitor_loop,
            name="sandbox-workspace-cleanup",
            daemon=True,
        )
        thread.start()
        _MONITOR_STARTED = True


@contextlib.contextmanager
def sandbox_tool_activity() -> Iterator[None]:
    """Track active tool calls so idle cleanup does not race tool execution."""

    global _ACTIVE_CALLS, _LAST_ACTIVITY_MONOTONIC
    ensure_cleanup_monitor_started()
    with _LOCK:
        _ACTIVE_CALLS += 1
        _LAST_ACTIVITY_MONOTONIC = time.monotonic()
    try:
        yield
    finally:
        with _LOCK:
            _ACTIVE_CALLS = max(0, _ACTIVE_CALLS - 1)
            _LAST_ACTIVITY_MONOTONIC = time.monotonic()
