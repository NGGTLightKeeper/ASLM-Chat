# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import json
import os
import platform
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEGACY_CONTROL_ROOT = PROJECT_ROOT / "Data" / "deep_research"


def _default_control_root() -> Path:
    override = str(os.environ.get("ASLM_DEEP_RESEARCH_RUNTIME_DIR") or "").strip()
    if override:
        return Path(os.path.expandvars(override)).expanduser()

    system = platform.system().lower()
    if system == "windows":
        local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / "ASLM-Chat" / "runtime" / "deep-research"
    if system == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "ASLM-Chat"
            / "runtime"
            / "deep-research"
        )

    xdg_state_home = str(os.environ.get("XDG_STATE_HOME") or "").strip()
    base = Path(xdg_state_home).expanduser() if xdg_state_home else Path.home() / ".local" / "state"
    return base / "aslm-chat" / "deep-research"


CONTROL_ROOT = _default_control_root()
STATE_ROOT = CONTROL_ROOT / "state"
COMMAND_ROOT = CONTROL_ROOT / "commands"

_MIGRATION_MARKER = ".legacy-data-migrated-v1.json"
_MIGRATION_LOCK = ".legacy-data-migration-v1.lock"
_RETENTION_LOCK = ".terminal-retention-v1.lock"
_MAINTENANCE_INTERVAL_SECONDS = 300.0
_LOCK_STALE_SECONDS = 120.0
_last_retention_check = 0.0

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


def _storage_root() -> Path:
    """Return the common root, including when tests replace the leaf roots."""

    if STATE_ROOT.parent == COMMAND_ROOT.parent:
        return STATE_ROOT.parent
    return CONTROL_ROOT


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    try:
        return max(minimum, int(str(os.environ.get(name) or default).strip()))
    except (TypeError, ValueError):
        return default


def _try_acquire_lease(path: Path) -> int | None:
    """Acquire a short cross-process lease without blocking request polling."""

    for attempt in range(2):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"{os.getpid()} {time.time()}\n".encode("ascii"))
            return descriptor
        except FileExistsError:
            if attempt:
                return None
            try:
                if time.time() - path.stat().st_mtime <= _LOCK_STALE_SECONDS:
                    return None
                path.unlink(missing_ok=True)
            except OSError:
                return None
        except OSError:
            return None
    return None


def _release_lease(path: Path, descriptor: int | None) -> None:
    if descriptor is None:
        return
    try:
        os.close(descriptor)
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _replace_with_retry(temporary_path: Path, destination: Path) -> None:
    for attempt in range(5):
        try:
            os.replace(temporary_path, destination)
            return
        except PermissionError:
            if attempt >= 4:
                raise
            time.sleep(0.01 * (attempt + 1))


def _atomic_copy(source: Path, destination: Path) -> bool:
    """Copy one legacy artifact through an atomic destination-side swap."""

    try:
        content = source.read_bytes()
    except OSError:
        # Antivirus/indexing can transiently lock files on Windows. Migration is
        # best-effort: leave this artifact in legacy storage and retry next time.
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}-",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as target_handle:
            target_handle.write(content)
            target_handle.flush()
            os.fsync(target_handle.fileno())
        _replace_with_retry(temporary_path, destination)
        return True
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def _json_timestamp(payload: Mapping[str, Any]) -> float:
    try:
        return float(payload.get("updated_at") or 0)
    except (TypeError, ValueError):
        return 0.0


def _same_file_payload(source: Path, destination: Path) -> bool:
    try:
        if source.read_bytes() == destination.read_bytes():
            return True
    except OSError:
        return False
    source_payload = _read_json(source)
    destination_payload = _read_json(destination)
    return bool(source_payload) and source_payload == destination_payload


def _remove_empty_legacy_directories() -> None:
    command_root = LEGACY_CONTROL_ROOT / "commands"
    if command_root.is_dir():
        for directory in command_root.iterdir():
            if directory.is_dir():
                try:
                    directory.rmdir()
                except OSError:
                    pass
    for directory in (
        LEGACY_CONTROL_ROOT / "state",
        command_root,
        LEGACY_CONTROL_ROOT,
    ):
        try:
            directory.rmdir()
        except OSError:
            pass


def _legacy_files(root: Path, pattern: str) -> list[Path]:
    try:
        return sorted(root.glob(pattern))
    except OSError:
        return []


def _legacy_files_remain(root: Path, pattern: str) -> bool:
    try:
        return any(root.glob(pattern))
    except OSError:
        return True


def _migrate_legacy_storage() -> None:
    """Move the old repository-local store once, preserving the newest snapshots."""

    root = _storage_root()
    # Replaced roots in tests and embedding applications must not unexpectedly
    # import the real repository's legacy data.
    if root != CONTROL_ROOT or LEGACY_CONTROL_ROOT == root:
        return
    marker = root / _MIGRATION_MARKER
    if marker.exists():
        return

    lock = root / _MIGRATION_LOCK
    descriptor = _try_acquire_lease(lock)
    deadline = time.monotonic() + 5.0
    while descriptor is None and not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
        descriptor = _try_acquire_lease(lock)
    if descriptor is None:
        return
    states_copied = 0
    commands_copied = 0
    try:
        if marker.exists():
            return
        legacy_state_root = LEGACY_CONTROL_ROOT / "state"
        if legacy_state_root.is_dir():
            for source in _legacy_files(legacy_state_root, "*.json"):
                destination = STATE_ROOT / source.name
                legacy_payload = _read_json(source)
                expected_payload: dict[str, Any] | None = None
                if destination.exists():
                    current_payload = _read_json(destination)
                    if legacy_payload and current_payload:
                        if _json_timestamp(current_payload) >= _json_timestamp(legacy_payload):
                            expected_payload = {**legacy_payload, **current_payload}
                        else:
                            expected_payload = {**current_payload, **legacy_payload}
                        _atomic_write_json(destination, expected_payload)
                    elif not _same_file_payload(source, destination):
                        # A malformed conflict cannot be merged safely. Leave the
                        # legacy artifact in place and retry on a later startup.
                        continue
                else:
                    if not _atomic_copy(source, destination):
                        continue
                    expected_payload = legacy_payload or None
                if legacy_payload:
                    if _read_json(destination) != (expected_payload or legacy_payload):
                        continue
                elif not _same_file_payload(source, destination):
                    continue
                try:
                    source.unlink(missing_ok=True)
                except OSError:
                    continue
                states_copied += 1

        legacy_command_root = LEGACY_CONTROL_ROOT / "commands"
        if legacy_command_root.is_dir():
            for source in _legacy_files(legacy_command_root, "*/*.json"):
                session_directory = source.parent.name
                if not re.fullmatch(r"[a-f0-9]{32}", session_directory, flags=re.I):
                    continue
                destination = COMMAND_ROOT / session_directory.lower() / source.name
                if not destination.exists():
                    if not _atomic_copy(source, destination):
                        continue
                if not _same_file_payload(source, destination):
                    continue
                try:
                    source.unlink(missing_ok=True)
                except OSError:
                    continue
                commands_copied += 1

        remaining_states = legacy_state_root.is_dir() and _legacy_files_remain(
            legacy_state_root,
            "*.json",
        )
        remaining_commands = legacy_command_root.is_dir() and _legacy_files_remain(
            legacy_command_root,
            "*/*.json",
        )
        if remaining_states or remaining_commands:
            return
        _atomic_write_json(
            marker,
            {
                "schema_version": 1,
                "migrated_at": time.time(),
                "legacy_root": str(LEGACY_CONTROL_ROOT),
                "states_moved": states_copied,
                "commands_moved": commands_copied,
            },
        )
        _remove_empty_legacy_directories()
    finally:
        _release_lease(lock, descriptor)


def _remove_command_directory(session_key_value: str) -> None:
    directory = COMMAND_ROOT / session_key_value
    if not directory.is_dir():
        return
    for path in directory.glob("*.json"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        directory.rmdir()
    except OSError:
        pass


def _cleanup_persisted_commands() -> None:
    """Drop commands durably acknowledged by a worker, including after restart."""

    try:
        directories = list(COMMAND_ROOT.iterdir())
    except OSError:
        return
    for directory in directories:
        if not directory.is_dir() or not re.fullmatch(
            r"[a-f0-9]{32}",
            directory.name,
            flags=re.I,
        ):
            continue
        snapshot = _read_json(STATE_ROOT / f"{directory.name.lower()}.json")
        if not snapshot:
            continue
        if is_terminal_status(snapshot.get("status")):
            _remove_command_directory(directory.name.lower())
            continue
        processed_values = snapshot.get("processed_commands")
        processed = {
            str(filename)
            for filename in processed_values
            if Path(str(filename or "")).name == str(filename or "")
            and str(filename or "").endswith(".json")
        } if isinstance(processed_values, list) else set()
        for filename in processed:
            try:
                (directory / filename).unlink(missing_ok=True)
            except OSError:
                pass
        try:
            directory.rmdir()
        except OSError:
            pass


def _apply_terminal_retention(*, force: bool = False) -> None:
    """Bound terminal snapshots by age and count while retaining every active run."""

    global _last_retention_check
    now = time.time()
    if not force and now - _last_retention_check < _MAINTENANCE_INTERVAL_SECONDS:
        return
    _last_retention_check = now

    root = _storage_root()
    lock = root / _RETENTION_LOCK
    descriptor = _try_acquire_lease(lock)
    if descriptor is None:
        return
    try:
        _cleanup_persisted_commands()
        retention_days = _env_int("ASLM_DEEP_RESEARCH_TERMINAL_RETENTION_DAYS", 30)
        retention_max = _env_int("ASLM_DEEP_RESEARCH_TERMINAL_RETENTION_MAX", 256)
        cutoff = now - (retention_days * 86400)
        terminal: list[tuple[float, Path, str]] = []
        for path in STATE_ROOT.glob("*.json"):
            if not re.fullmatch(r"[a-f0-9]{32}", path.stem, flags=re.I):
                continue
            payload = _read_json(path)
            if not payload or not is_terminal_status(payload.get("status")):
                continue
            try:
                updated_at = float(payload.get("updated_at") or path.stat().st_mtime)
            except (OSError, TypeError, ValueError):
                updated_at = now
            terminal.append((updated_at, path, path.stem.lower()))

        terminal.sort(key=lambda item: item[0], reverse=True)
        expired = {
            path
            for index, (updated_at, path, _key) in enumerate(terminal)
            if updated_at < cutoff or index >= retention_max
        }
        for _updated_at, path, key in terminal:
            if path not in expired:
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue
            _remove_command_directory(key)
    finally:
        _release_lease(lock, descriptor)


def _ensure_roots() -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    COMMAND_ROOT.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_storage()
    _apply_terminal_retention()


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
        # Windows can briefly lock the destination while another process polls
        # it; retry the atomic swap without losing the previous snapshot.
        _replace_with_retry(temporary_path, path)
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


def _checklist_title_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _merge_checklist_snapshot(previous: Any, current: Any) -> list[dict[str, Any]]:
    """Prevent a stale worker checkpoint from undoing accepted progress."""

    previous_items = (
        [dict(item) for item in previous if isinstance(item, dict)]
        if isinstance(previous, list)
        else []
    )
    current_items = (
        [dict(item) for item in current if isinstance(item, dict)]
        if isinstance(current, list)
        else []
    )
    if not current_items:
        return previous_items

    previous_by_id = {
        str(item.get("id") or ""): item
        for item in previous_items
        if str(item.get("id") or "")
    }
    previous_by_title: dict[str, dict[str, Any]] = {}
    duplicate_titles: set[str] = set()
    for item in previous_items:
        title_key = _checklist_title_key(item.get("title"))
        if not title_key:
            continue
        if title_key in previous_by_title:
            duplicate_titles.add(title_key)
        else:
            previous_by_title[title_key] = item
    for title_key in duplicate_titles:
        previous_by_title.pop(title_key, None)
    output: list[dict[str, Any]] = []
    for item in current_items:
        item_id = str(item.get("id") or "")
        title_key = _checklist_title_key(item.get("title"))
        prior = previous_by_id.get(item_id)
        if prior is not None and _checklist_title_key(prior.get("title")) != title_key:
            prior = None
        if prior is None:
            prior = previous_by_title.get(title_key)
        prior_status = str((prior or {}).get("status") or "pending").strip().lower()
        current_status = str(item.get("status") or "pending").strip().lower()
        if prior_status in {"done", "skipped"} and current_status not in {"done", "skipped"}:
            item["status"] = prior_status
            if (
                not str(item.get("note") or "").strip()
                and str((prior or {}).get("note") or "").strip()
            ):
                item["note"] = str(prior.get("note"))[:300]
        output.append(item)
    return output


def update_state(session_id: Any, **changes: Any) -> dict[str, Any]:
    """Merge a worker checkpoint into the current durable snapshot."""

    _ensure_roots()
    normalized_id = f"deep-research:{session_key(session_id)}"
    path = _state_path(normalized_id)
    snapshot = _read_json(path)
    if not snapshot:
        snapshot = create_session(normalized_id, topic=str(changes.get("topic") or ""))
    if "checklist" in changes:
        changes["checklist"] = _merge_checklist_snapshot(
            snapshot.get("checklist"),
            changes.get("checklist"),
        )
    current_status = str(snapshot.get("status") or "").strip().lower()
    incoming_status = str(changes.get("status") or "").strip().lower()
    if current_status == "stopping" and not is_terminal_status(incoming_status):
        # The UI persists ``stopping`` before aborting the worker. A checkpoint
        # already in flight must not resurrect its stale controls on poll/reload.
        for protected_key in (
            "status",
            "phase",
            "can_stop",
            "can_edit",
            "can_approve",
        ):
            changes.pop(protected_key, None)
    snapshot.update(changes)
    snapshot["schema_version"] = 1
    snapshot["session_id"] = normalized_id
    snapshot["updated_at"] = time.time()
    _atomic_write_json(path, snapshot)
    if is_terminal_status(snapshot.get("status")):
        # Once the terminal snapshot is durable, commands cannot affect this run
        # anymore and keeping their immutable inbox only leaks runtime files.
        _remove_command_directory(session_key(normalized_id))
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

    A command stays durable until the worker includes its filename in ``processed``.
    A later poll removes those acknowledged files, retaining crash-safe replay without
    turning the command inbox into a permanent log archive.
    """

    directory = _command_dir(session_id)
    if not directory.is_dir():
        return []
    seen = processed if isinstance(processed, set) else set()
    for filename in seen:
        safe_name = Path(str(filename or "")).name
        if safe_name != str(filename or "") or not safe_name.endswith(".json"):
            continue
        try:
            (directory / safe_name).unlink(missing_ok=True)
        except OSError:
            pass
    output: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
        if path.name in seen:
            continue
        command = _read_json(path)
        if command:
            output.append((path.name, command))
    if not output:
        try:
            directory.rmdir()
        except OSError:
            pass
    return output


def latest_cancel_requested(session_id: Any) -> bool:
    return any(
        str(command.get("action") or "").strip().lower() == "cancel"
        for _name, command in read_commands(session_id)
    )
