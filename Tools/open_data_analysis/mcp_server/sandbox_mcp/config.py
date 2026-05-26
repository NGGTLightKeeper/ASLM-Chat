"""Runtime configuration shared by MCP, daemon, CLI, and future UI adapters."""
from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path

from sandbox_mcp.files import tmp_root

DEFAULT_DAEMON_HOST = "127.0.0.1"
DEFAULT_DAEMON_PORT = 20002
ASLM_DAEMON_PORT_KEY = "oda-daemon-port"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, min_v: int, max_v: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except ValueError:
        value = default
    return max(min_v, min(max_v, value))


def _coerce_port(value: object, default: int) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(65535, port))


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _aslm_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "ASLM_Module.json").is_file():
            return parent
    return None


def _manifest_setting_value(manifest: dict, key: str) -> object | None:
    settings = manifest.get("settings")
    if not isinstance(settings, list):
        return None
    for item in settings:
        if isinstance(item, dict) and item.get("key") == key:
            return item.get("value", item.get("default"))
    return None


def _configured_daemon_port() -> int:
    aslm_env = os.environ.get("ASLM_ODA_DAEMON_PORT")
    if aslm_env:
        return _coerce_port(aslm_env, DEFAULT_DAEMON_PORT)

    root = _aslm_root()
    if root is None:
        return DEFAULT_DAEMON_PORT

    settings = _load_json(root / "Settings" / "settings.json")
    if ASLM_DAEMON_PORT_KEY in settings:
        return _coerce_port(settings.get(ASLM_DAEMON_PORT_KEY), DEFAULT_DAEMON_PORT)

    manifest = _load_json(root / "ASLM_Module.json")
    return _coerce_port(_manifest_setting_value(manifest, ASLM_DAEMON_PORT_KEY), DEFAULT_DAEMON_PORT)


@dataclass(frozen=True)
class DaemonConfig:
    host: str
    port: int
    url: str
    use_daemon: bool
    autostart: bool
    state_path: Path
    log_path: Path
    startup_lock_path: Path
    cleanup_interval_seconds: int


def daemon_config() -> DaemonConfig:
    host = os.environ.get("SANDBOX_DAEMON_HOST", DEFAULT_DAEMON_HOST).strip() or DEFAULT_DAEMON_HOST
    port = _env_int("SANDBOX_DAEMON_PORT", _configured_daemon_port(), min_v=1, max_v=65535)
    raw_url = os.environ.get("SANDBOX_DAEMON_URL", "").strip().rstrip("/")
    url = raw_url or f"http://{host}:{port}"

    use_flag = _truthy(os.environ.get("SANDBOX_USE_DAEMON"))
    autostart_flag = _truthy(os.environ.get("SANDBOX_DAEMON_AUTOSTART"))
    use_daemon = bool(raw_url) or use_flag or autostart_flag
    autostart = autostart_flag or (use_flag and not raw_url)

    state_raw = os.environ.get("SANDBOX_STATE_PATH", "").strip()
    state_path = Path(state_raw).expanduser().resolve() if state_raw else tmp_root() / "state.json"

    log_raw = os.environ.get("SANDBOX_DAEMON_LOG", "").strip()
    log_path = Path(log_raw).expanduser().resolve() if log_raw else tmp_root() / "sandboxd.log"

    lock_raw = os.environ.get("SANDBOX_DAEMON_STARTUP_LOCK", "").strip()
    startup_lock_path = (
        Path(lock_raw).expanduser().resolve()
        if lock_raw
        else tmp_root() / f"sandboxd-{host}-{port}.lock"
    )

    cleanup_interval_seconds = _env_int(
        "SANDBOX_DAEMON_CLEANUP_INTERVAL_SECONDS",
        60,
        min_v=5,
        max_v=24 * 60 * 60,
    )

    return DaemonConfig(
        host=host,
        port=port,
        url=url,
        use_daemon=use_daemon,
        autostart=autostart,
        state_path=state_path,
        log_path=log_path,
        startup_lock_path=startup_lock_path,
        cleanup_interval_seconds=cleanup_interval_seconds,
    )
