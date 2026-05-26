#!/usr/bin/env python3
"""Generate or update mcp.json for the ODA MCP server."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ASLM_ROOT = ROOT.parent.parent
MCP_SERVER = ROOT / "mcp_server"
TMP_ROOT = ROOT / "tmp"
SHARED_ROOT = TMP_ROOT / "_sandbox"
DEFAULT_DAEMON_HOST = "127.0.0.1"
DEFAULT_DAEMON_PORT = 20002
ASLM_DAEMON_PORT_KEY = "oda-daemon-port"


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
    for parent in ROOT.parents:
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


def _detect_python() -> Path:
    managed_venv = ASLM_ROOT / "Data" / "venvs" / "tools" / "open_data_analysis"
    if sys.platform.startswith("win"):
        candidates = [
            managed_venv / "Scripts" / "python.exe",
            MCP_SERVER / ".venv" / "Scripts" / "python.exe",
            ROOT / ".venv" / "Scripts" / "python.exe",
        ]
    else:
        candidates = [
            managed_venv / "bin" / "python",
            MCP_SERVER / ".venv" / "bin" / "python",
            ROOT / ".venv" / "bin" / "python",
        ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def _target_path(target: str, output: str | None) -> Path:
    if output:
        return Path(output).expanduser().resolve()
    if target == "cursor":
        return (Path.home() / ".cursor" / "mcp.json").resolve()
    if target == "lmstudio":
        return (Path.home() / ".lmstudio" / "mcp.json").resolve()
    if target == "project":
        return (ROOT / ".cursor" / "mcp.json").resolve()
    raise SystemExit("Unknown target. Use --target cursor|lmstudio|project or pass --output PATH.")


def _load_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _server_entry(
    python_exe: Path,
    *,
    image: str,
    tmp_root: Path | None,
    shared_root: Path,
    timeout_sec: int,
    timeout_ms: int,
    use_daemon: bool,
    daemon_autostart: bool,
    daemon_host: str,
    daemon_port: int,
    daemon_url: str | None,
) -> dict:
    env = {
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "SANDBOX_IMAGE": image,
        "SANDBOX_SHARED_ROOT": str(shared_root.resolve()),
        "SANDBOX_TIMEOUT": str(timeout_sec),
        "SANDBOX_MAX_CONCURRENT": "1",
        "SANDBOX_MCP_SERVER_ROOT": str(MCP_SERVER.resolve()),
        "SANDBOX_PYTHON": str(python_exe),
    }
    if tmp_root is not None:
        env["SANDBOX_TMP_ROOT"] = str(tmp_root.resolve())
    if use_daemon:
        env["SANDBOX_USE_DAEMON"] = "1"
        env["SANDBOX_DAEMON_HOST"] = daemon_host
        env["SANDBOX_DAEMON_PORT"] = str(daemon_port)
    if daemon_autostart:
        env["SANDBOX_DAEMON_AUTOSTART"] = "1"
    if daemon_url:
        env["SANDBOX_DAEMON_URL"] = daemon_url.rstrip("/")

    return {
        "command": str(python_exe),
        "args": ["-m", "sandbox_mcp"],
        "cwd": str(MCP_SERVER),
        "env": env,
        "timeout": timeout_ms,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate or update mcp.json for the ODA MCP server."
    )
    parser.add_argument(
        "--target",
        choices=["cursor", "lmstudio", "project"],
        default="cursor",
        help="Where to write mcp.json if --output is not set. Default: cursor",
    )
    parser.add_argument(
        "--output",
        help="Write to an explicit path instead of a predefined target.",
    )
    parser.add_argument(
        "--server-name",
        default="oda",
        help="Server key inside mcpServers. Default: oda",
    )
    parser.add_argument(
        "--image",
        default="sandbox:latest",
        help="Docker image tag. Default: sandbox:latest",
    )
    parser.add_argument(
        "--tmp-root",
        type=Path,
        default=None,
        help=(
            "Parent directory for runs/staging/artifacts/archive. "
            "Default: unset, so runtime uses the OS temp directory."
        ),
    )
    parser.add_argument(
        "--shared-root",
        type=Path,
        default=SHARED_ROOT,
        help="Host-visible _sandbox directory. Default: <repo>/Tools/open_data_analysis/tmp/_sandbox",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Sandbox command timeout in seconds. Default: 300",
    )
    parser.add_argument(
        "--mcp-timeout-ms",
        type=int,
        default=360_000,
        help="MCP server timeout in milliseconds. Default: 360000",
    )
    parser.add_argument(
        "--use-daemon",
        action="store_true",
        default=True,
        help="Route MCP calls through sandboxd (default: on).",
    )
    parser.add_argument(
        "--no-daemon",
        dest="use_daemon",
        action="store_false",
        help="Disable daemon routing.",
    )
    parser.add_argument(
        "--daemon-autostart",
        action="store_true",
        default=True,
        help="Let MCP lazily start sandboxd on the first sandbox call (default: on).",
    )
    parser.add_argument(
        "--no-daemon-autostart",
        dest="daemon_autostart",
        action="store_false",
        help="Disable daemon autostart.",
    )
    parser.add_argument(
        "--daemon-host",
        default=DEFAULT_DAEMON_HOST,
        help="sandboxd host. Default: 127.0.0.1",
    )
    parser.add_argument(
        "--daemon-port",
        type=int,
        default=None,
        help=f"sandboxd port. Default: ASLM setting '{ASLM_DAEMON_PORT_KEY}'",
    )
    parser.add_argument(
        "--daemon-url",
        help="Explicit sandboxd URL. If set without --daemon-autostart, MCP will not spawn a daemon.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print JSON to stdout instead of writing to a file.",
    )
    args = parser.parse_args()

    python_exe = _detect_python()
    tmp_root = args.tmp_root.expanduser().resolve() if args.tmp_root else None
    shared_root = args.shared_root.expanduser().resolve()
    shared_root.mkdir(parents=True, exist_ok=True)
    if tmp_root is not None:
        tmp_root.mkdir(parents=True, exist_ok=True)
    daemon_port = args.daemon_port or _configured_daemon_port()

    payload = {
        "mcpServers": {
            args.server_name: _server_entry(
                python_exe,
                image=args.image,
                tmp_root=tmp_root,
                shared_root=shared_root,
                timeout_sec=args.timeout,
                timeout_ms=args.mcp_timeout_ms,
                use_daemon=args.use_daemon or args.daemon_autostart or bool(args.daemon_url),
                daemon_autostart=args.daemon_autostart,
                daemon_host=args.daemon_host,
                daemon_port=daemon_port,
                daemon_url=args.daemon_url,
            ),
        }
    }

    if args.stdout:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    target = _target_path(args.target, args.output)
    existing = _load_existing(target)
    merged = dict(existing) if isinstance(existing, dict) else {}
    servers = merged.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers[args.server_name] = payload["mcpServers"][args.server_name]
    merged["mcpServers"] = servers

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Python   : {python_exe}")
    print(f"MCP root : {MCP_SERVER}")
    print(f"Tmp root : {tmp_root or Path(tempfile.gettempdir()) / 'oda-sandbox'}")
    print(f"Shared   : {shared_root}")
    print(f"Image    : {args.image}")
    daemon_enabled = args.use_daemon or args.daemon_autostart or bool(args.daemon_url)
    print(f"Daemon   : {args.daemon_url or f'http://{args.daemon_host}:{daemon_port}'} (enabled={daemon_enabled})")
    print(f"Autostart: {bool(args.daemon_autostart)}")
    print(f"Target   : {target}")
    print(f"Server   : {args.server_name}")
    print("Done.")


if __name__ == "__main__":
    main()
