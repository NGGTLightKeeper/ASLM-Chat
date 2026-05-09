# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Standalone sandbox image setup script.

Run this once before first use, or whenever the image needs to be refreshed.
Works independently of the ASLM / MCP stack — only requires Docker.

Usage:
    python setup-sandbox.py [--source local|registry|auto] [--force]

Exit codes:
    0  — image is ready
    1  — setup failed (details printed to stderr)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# ── Resolve image name from sandbox.env if present ──────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent
_ENV_FILE = _SCRIPT_DIR / "sandbox.env"

_DEFAULT_IMAGE = "dima1312313/mcp-sandbox:latest"
_REQUIRED_LABEL = "org.aslm.sandbox.supervisor-runtime"
_REQUIRED_LABEL_VALUE = "container-v2"

_CONFIG_TEMPLATE = """\
# sandbox.env - generated automatically on first launch.
# Uncomment and edit any line to override the default without rebuilding the image.
# Changes take effect the next time the container is (re)started.

# === Container identity ===
#SANDBOX_CONTAINER_NAME=mcp-sandbox
#SANDBOX_IMAGE=dima1312313/mcp-sandbox:latest
#SANDBOX_IMAGE_SOURCE=registry

# === Resource limits (applied at docker run) ===
#SANDBOX_CPU_LIMIT=4
#SANDBOX_MEMORY_LIMIT=3g
#SANDBOX_MEMORY_SWAP_LIMIT=4g
#SANDBOX_PIDS_LIMIT=256
#SANDBOX_STORAGE_LIMIT=12G
#SANDBOX_NETWORK_LIMIT_MBIT=100

# === Execution limits (inside container) ===
#SANDBOX_DEFAULT_TIMEOUT=60
#SANDBOX_MAX_OUTPUT_BYTES=60000
#SANDBOX_OUTPUT_HEAD_RATIO=0.5
#SANDBOX_MAX_READ_BYTES=200000
#SANDBOX_MAX_CAT_FILE_BYTES=30720
#SANDBOX_MAX_CAT_LINE_THRESHOLD=300
#SANDBOX_MAX_IMAGE_PREVIEW_BYTES=2000000
#SANDBOX_MAX_LS_ENTRIES=500
#SANDBOX_MAX_FIND_RESULTS=200
#SANDBOX_MAX_GREP_RESULTS=200
#SANDBOX_BACKGROUND_TIMEOUT_THRESHOLD=10

# === Thread limits ===
#SANDBOX_THREAD_LIMIT=4

# === Workspace ===
#SANDBOX_DEFAULT_TASK_DIR=_sandbox
#SANDBOX_WORKSPACE_CLEANUP_ENABLED=1
#SANDBOX_WORKSPACE_CLEANUP_IDLE_SECONDS=5400
#SANDBOX_WORKSPACE_CLEANUP_RECYCLE_SECONDS=10800
#SANDBOX_WORKSPACE_CLEANUP_INTERVAL_SECONDS=5

#SANDBOX_MAX_FILE_MAP_SYMBOLS=50

# === Docker startup ===
#SANDBOX_DOCKER_START_TIMEOUT_SECONDS=60
"""


def _ensure_env_file(path: Path) -> None:
    if path.exists():
        return
    try:
        path.write_text(_CONFIG_TEMPLATE, encoding="utf-8")
    except OSError:
        pass


def _load_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    except OSError:
        pass
    return result


_ensure_env_file(_ENV_FILE)
_env_overrides = _load_env_file(_ENV_FILE)


def _cfg(key: str, default: str) -> str:
    return os.environ.get(key) or _env_overrides.get(key) or default


SANDBOX_IMAGE = _cfg("SANDBOX_IMAGE", _DEFAULT_IMAGE)


# ── Helpers ──────────────────────────────────────────────────────────

def _run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )


def _stream(args: list[str], timeout: int = 1800) -> int:
    """Run a command with real-time stdout/stderr visible to the user."""
    proc = subprocess.run(args, timeout=timeout)
    return proc.returncode


def _ok(msg: str) -> None:
    print(f"  [ok] {msg}", flush=True)


def _info(msg: str) -> None:
    print(f"  ... {msg}", flush=True)


def _fail(msg: str) -> None:
    print(f"  [!!] {msg}", file=sys.stderr, flush=True)


# ── Docker checks ────────────────────────────────────────────────────

def _check_docker() -> bool:
    try:
        r = _run(["docker", "--version"], timeout=5)
        if r.returncode != 0:
            _fail("Docker CLI found but returned an error.")
            return False
        _ok(r.stdout.strip())
        return True
    except FileNotFoundError:
        _fail("Docker CLI not found. Install Docker Desktop and try again.")
        return False
    except Exception as exc:
        _fail(f"Unexpected error checking docker: {exc}")
        return False


def _check_daemon() -> bool:
    try:
        r = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=10)
        if r.returncode == 0:
            _ok(f"Docker daemon running (server {r.stdout.strip()})")
            return True
        _fail("Docker daemon is not running. Start Docker Desktop and try again.")
        return False
    except Exception as exc:
        _fail(f"Cannot reach Docker daemon: {exc}")
        return False


# ── Image checks ─────────────────────────────────────────────────────

def _image_exists_and_valid() -> bool:
    r = _run(["docker", "image", "inspect", SANDBOX_IMAGE], timeout=10)
    if r.returncode != 0:
        return False
    import json
    try:
        data = json.loads(r.stdout)
        labels = (data[0].get("Config", {}).get("Labels") or {}) if data else {}
        return labels.get(_REQUIRED_LABEL) == _REQUIRED_LABEL_VALUE
    except Exception:
        return False


# ── Pull / build ─────────────────────────────────────────────────────

def _pull() -> bool:
    _info(f"Pulling {SANDBOX_IMAGE} from Docker Hub...")
    code = _stream(["docker", "pull", SANDBOX_IMAGE], timeout=600)
    if code == 0:
        if _image_exists_and_valid():
            _ok("Image pulled and validated.")
            return True
        _fail("Image pulled but missing required runtime label — needs rebuild.")
        return False
    _fail("Pull failed.")
    return False


def _build() -> bool:
    dockerfile_path = _SCRIPT_DIR / "Dockerfile"
    if not dockerfile_path.exists():
        _fail(f"Dockerfile not found at {dockerfile_path}")
        return False
    _info(f"Building {SANDBOX_IMAGE} from local Dockerfile (this may take 10–20 min)...")
    code = _stream(
        ["docker", "build", "-t", SANDBOX_IMAGE, str(_SCRIPT_DIR)],
        timeout=1800,
    )
    if code == 0:
        _ok("Image built successfully.")
        return True
    _fail("Local build failed. Check the output above for details.")
    return False


# ── Main ─────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Set up the mcp-sandbox Docker image.")
    parser.add_argument(
        "--source",
        choices=["local", "registry", "auto"],
        default=None,
        help="Image source: local=build only, registry=pull only, auto=pull then build (default: from sandbox.env or 'auto')",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-pull / rebuild even if a valid image already exists locally.",
    )
    args = parser.parse_args()

    source = args.source or _cfg("SANDBOX_IMAGE_SOURCE", "auto")
    if source not in {"local", "registry", "auto"}:
        source = "auto"

    print(f"\nmcp-sandbox image setup", flush=True)
    print(f"  image  : {SANDBOX_IMAGE}", flush=True)
    print(f"  source : {source}", flush=True)
    print(flush=True)

    # 1. Docker availability
    print("Checking Docker...", flush=True)
    if not _check_docker():
        return 1
    if not _check_daemon():
        return 1
    print(flush=True)

    # 2. Already have a valid image?
    if not args.force and _image_exists_and_valid():
        _ok(f"Image '{SANDBOX_IMAGE}' already present and valid. Nothing to do.")
        print(flush=True)
        return 0

    if args.force:
        _info("--force: skipping existing image check.")

    # 3. Pull / build according to source
    print("Fetching image...", flush=True)
    if source == "local":
        success = _build() or _pull()
    elif source == "registry":
        success = _pull() or _build()
    else:  # auto
        success = _pull() or _build()

    print(flush=True)
    if success:
        print("Setup complete. You can now start the sandbox.", flush=True)
        return 0
    else:
        print("Setup failed. See errors above.", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
