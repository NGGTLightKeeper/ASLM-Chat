#!/usr/bin/env python3
"""Generate or update mcp.json for this mcp-web-search server."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _detect_python() -> Path:
    if sys.platform.startswith("win"):
        candidates = [
            ROOT / ".venv" / "Scripts" / "python.exe",
            ROOT / "test_directory" / "mcp-web-search" / ".venv" / "Scripts" / "python.exe",
        ]
    else:
        candidates = [
            ROOT / ".venv" / "bin" / "python",
            ROOT / "test_directory" / "mcp-web-search" / ".venv" / "bin" / "python",
        ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def _target_path(target: str, output: str | None) -> Path:
    if output:
        return Path(output).expanduser().resolve()
    if target == "lmstudio":
        return (Path.home() / ".lmstudio" / "mcp.json").resolve()
    if target == "project":
        return (ROOT / "mcp.json").resolve()
    raise SystemExit("Unknown target. Use --target lmstudio|project or pass --output PATH.")


def _load_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _server_entry(python_exe: Path, timeout_ms: int) -> dict:
    return {
        "command": str(python_exe),
        "args": ["-m", "adapters.mcp.server"],
        "cwd": str(ROOT),
        "env": {
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        },
        "timeout": timeout_ms,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate or update mcp.json for mcp-web-search."
    )
    parser.add_argument(
        "--target",
        choices=["lmstudio", "project"],
        default="project",
        help="Where to place mcp.json if --output is not given. Default: project",
    )
    parser.add_argument(
        "--output",
        help="Write to an explicit path instead of a predefined target.",
    )
    parser.add_argument(
        "--server-name",
        default="mcp-web-search",
        help="Server key inside mcpServers. Default: mcp-web-search",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120_000,
        help="Server timeout in milliseconds. Default: 120000",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print JSON to stdout instead of writing to a file.",
    )
    args = parser.parse_args()

    python_exe = _detect_python()
    payload = {
        "mcpServers": {
            args.server_name: _server_entry(python_exe, args.timeout),
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

    print(f"Python : {python_exe}")
    print(f"Root   : {ROOT}")
    print(f"Target : {target}")
    print(f"Server : {args.server_name}")
    print("Done.")


if __name__ == "__main__":
    main()
