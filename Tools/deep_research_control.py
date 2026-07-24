"""Durable, process-safe control snapshots for Deep Research sessions.

The Deep Research MCP tool runs in a fresh worker process while the UI API runs in
the Django process.  Small atomic JSON files give both processes a shared approval,
revision, cancellation, and progress channel without keeping an in-memory registry
that would disappear on reload.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTROL_ROOT = PROJECT_ROOT / "Data" / "deep_research"
STATE_ROOT = CONTROL_ROOT / "state"
COMMAND_ROOT = CONTROL_ROOT / "commands"

_SESSION_RE = re.compile(r"^deep-research:([a-f0-9]{32})$", flags=re.I)
_TERMINAL_STATUSES = {"completed", "partial", "cancelled", "failed", "expired"}


class InvalidResearchSession(ValueError):
    """Raised when a caller supplies an unsafe or malformed session id."""


def new_session_id() -> str:
    return f"deep-research:{uuid.uuid4().hex}"


def session_key(session_id: Any) -> str:
    raw = str(session_id or "").strip()
    match = _SESSION_RE.fullmatch(raw)
    if not match:
        raise InvalidResearchSession("Invalid deep research session id.")
    return match.group(1).lower()


def is_terminal_status(status: Any) -> bool:
    return str(status or "").strip().lower() in _TERMINAL_STATUSES


def _ensure_roots() -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    COMMAND_ROOT.mkdir(parents=True, exist_ok=True)


def _state_path(session_id: Any) -> Path:
    return STATE_ROOT / f"{session_key(session_id)}.json"


def _command_dir(session_id: Any) -> Path:
    return COMMAND_ROOT / session_key(session_id)


def _read_json(path: Path) -> dict[str, Any]:
    for attempt in range(5):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            if attempt >= 4:
                return {}
            # A worker may be atomically swapping this snapshot while Django
            # polls it. Windows can expose a very short sharing violation.
            time.sleep(0.005 * (attempt + 1))
    return {}


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}-",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(dict(payload), handle, ensure_ascii=False, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(5):
            try:
                os.replace(temporary_path, path)
                break
            except PermissionError:
                if attempt >= 4:
                    raise
                # Windows can briefly lock the destination while another
                # process polls it; retry the atomic swap without losing state.
                time.sleep(0.01 * (attempt + 1))
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def create_session(
    session_id: Any,
    *,
    topic: str,
    status: str = "planning",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create the first snapshot if it does not already exist."""

    _ensure_roots()
    normalized_id = f"deep-research:{session_key(session_id)}"
    path = _state_path(normalized_id)
    existing = _read_json(path)
    if existing:
        return existing

    now = time.time()
    snapshot: dict[str, Any] = {
        "schema_version": 1,
        "session_id": normalized_id,
        "status": str(status or "planning"),
        "phase": str(status or "planning"),
        "topic": str(topic or "").strip(),
        "plan": "",
        "plan_version": 0,
        "checklist": [],
        "latest_action": "Preparing the research plan",
        "source_count": 0,
        "queries_used": 0,
        "query_budget": 0,
        "iteration": 0,
        "last_sequence": 0,
        "created_at": now,
        "updated_at": now,
    }
    if isinstance(extra, Mapping):
        snapshot.update(dict(extra))
    _atomic_write_json(path, snapshot)
    return snapshot


def read_state(session_id: Any) -> dict[str, Any]:
    _ensure_roots()
    return _read_json(_state_path(session_id))


def update_state(session_id: Any, **changes: Any) -> dict[str, Any]:
    """Merge a worker checkpoint into the current durable snapshot."""

    _ensure_roots()
    normalized_id = f"deep-research:{session_key(session_id)}"
    path = _state_path(normalized_id)
    snapshot = _read_json(path)
    if not snapshot:
        snapshot = create_session(normalized_id, topic=str(changes.get("topic") or ""))
    snapshot.update(changes)
    snapshot["schema_version"] = 1
    snapshot["session_id"] = normalized_id
    snapshot["updated_at"] = time.time()
    _atomic_write_json(path, snapshot)
    return snapshot


def submit_command(
    session_id: Any,
    action: str,
    *,
    payload: Mapping[str, Any] | None = None,
    expected_plan_version: int | None = None,
) -> dict[str, Any]:
    """Append one immutable UI command for the worker to consume."""

    normalized_id = f"deep-research:{session_key(session_id)}"
    normalized_action = str(action or "").strip().lower()
    if normalized_action not in {"approve", "revise", "cancel"}:
        raise ValueError("Unsupported deep research action.")

    snapshot = read_state(normalized_id)
    if not snapshot:
        raise FileNotFoundError("Deep research session was not found.")
    if is_terminal_status(snapshot.get("status")):
        return {
            "accepted": normalized_action == "cancel",
            "terminal": True,
            "state": snapshot,
        }
    if normalized_action == "approve" and snapshot.get("can_approve") is False:
        raise RuntimeError("ACTION_NOT_AVAILABLE")
    if normalized_action == "revise" and snapshot.get("can_edit") is False:
        raise RuntimeError("ACTION_NOT_AVAILABLE")

    current_version = int(snapshot.get("plan_version") or 0)
    # Stop must remain idempotent and immediately acceptable even if a newer
    # plan snapshot reached the worker just before the user's click.
    if (
        normalized_action != "cancel"
        and expected_plan_version is not None
        and int(expected_plan_version) != current_version
    ):
        raise RuntimeError("STALE_PLAN_VERSION")

    command = {
        "schema_version": 1,
        "command_id": uuid.uuid4().hex,
        "session_id": normalized_id,
        "action": normalized_action,
        "expected_plan_version": current_version,
        "payload": dict(payload or {}),
        "created_at": time.time(),
        "created_at_ns": time.time_ns(),
    }
    directory = _command_dir(normalized_id)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{command['created_at_ns']:020d}-{command['command_id']}.json"
    _atomic_write_json(directory / filename, command)
    return {"accepted": True, "terminal": False, "command": command, "state": snapshot}


def read_commands(
    session_id: Any,
    *,
    processed: set[str] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Read unprocessed commands in creation order.

    Files are intentionally retained for diagnostics and reload recovery.  The worker
    keeps the returned filenames in memory so replay remains explicit and idempotent.
    """

    directory = _command_dir(session_id)
    if not directory.is_dir():
        return []
    seen = processed if isinstance(processed, set) else set()
    output: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
        if path.name in seen:
            continue
        command = _read_json(path)
        if command:
            output.append((path.name, command))
    return output


def latest_cancel_requested(session_id: Any) -> bool:
    return any(
        str(command.get("action") or "").strip().lower() == "cancel"
        for _name, command in read_commands(session_id)
    )
