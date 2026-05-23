# Copyright NGGT.LightKeeper. All Rights Reserved.

"""Standalone ODA sandbox image setup script.

Run this once before first use, or let the ODA runner call it lazily.
Only Docker is required.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR / "oda-sandbox.env"

DEFAULT_IMAGE = "sandbox:latest"
REQUIRED_LABEL = "org.aslm.oda.sandbox-runtime"
REQUIRED_LABEL_VALUE = "container-v1"

CONFIG_TEMPLATE = """\
# oda-sandbox.env - generated automatically on first launch.
# Uncomment and edit any line to override the default without rebuilding the image.
# Changes take effect the next time the container is (re)started.

#SANDBOX_IMAGE=sandbox:latest
#SANDBOX_IMAGE_SOURCE=auto
"""


def _ensure_env_file(path: Path) -> None:
    if path.exists():
        return
    try:
        path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    except OSError:
        pass


def _load_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return result

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


_ensure_env_file(ENV_FILE)
_ENV_OVERRIDES = _load_env_file(ENV_FILE)


def _cfg(key: str, default: str) -> str:
    return os.environ.get(key) or _ENV_OVERRIDES.get(key) or default


SANDBOX_IMAGE = _cfg("SANDBOX_IMAGE", DEFAULT_IMAGE)


def _run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _stream(args: list[str], timeout: int = 1800) -> int:
    proc = subprocess.run(args, timeout=timeout)
    return proc.returncode


def _ok(message: str) -> None:
    print(f"  [ok] {message}", flush=True)


def _info(message: str) -> None:
    print(f"  ... {message}", flush=True)


def _fail(message: str) -> None:
    print(f"  [!!] {message}", file=sys.stderr, flush=True)


def _check_docker() -> bool:
    try:
        result = _run(["docker", "--version"], timeout=5)
    except FileNotFoundError:
        _fail("Docker CLI not found. Install Docker Desktop and try again.")
        return False
    except Exception as exc:
        _fail(f"Unexpected error checking Docker: {exc}")
        return False

    if result.returncode != 0:
        _fail("Docker CLI found but returned an error.")
        return False
    _ok(result.stdout.strip())
    return True


def _check_daemon() -> bool:
    try:
        result = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=10)
    except Exception as exc:
        _fail(f"Cannot reach Docker daemon: {exc}")
        return False

    if result.returncode == 0:
        _ok(f"Docker daemon running (server {result.stdout.strip()})")
        return True

    _fail("Docker daemon is not running. Start Docker Desktop and try again.")
    return False


def _image_exists_and_valid() -> bool:
    result = _run(["docker", "image", "inspect", SANDBOX_IMAGE], timeout=10)
    if result.returncode != 0:
        return False

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False

    if not isinstance(data, list) or not data:
        return False

    labels = data[0].get("Config", {}).get("Labels") or {}
    return labels.get(REQUIRED_LABEL) == REQUIRED_LABEL_VALUE


def _pull() -> bool:
    _info(f"Pulling {SANDBOX_IMAGE} from registry...")
    code = _stream(["docker", "pull", SANDBOX_IMAGE], timeout=600)
    if code != 0:
        _fail("Pull failed.")
        return False

    if _image_exists_and_valid():
        _ok("Image pulled and validated.")
        return True

    _fail("Image pulled but missing required ODA runtime label; needs rebuild.")
    return False


def _build() -> bool:
    dockerfile_path = SCRIPT_DIR / "sandbox" / "Dockerfile"
    if not dockerfile_path.exists():
        _fail(f"Dockerfile not found at {dockerfile_path}")
        return False

    _info(f"Building {SANDBOX_IMAGE} from local Dockerfile...")
    code = _stream(
        ["docker", "build", "-f", str(dockerfile_path), "-t", SANDBOX_IMAGE, str(SCRIPT_DIR)],
        timeout=1800,
    )
    if code != 0:
        _fail("Local build failed. Check the output above for details.")
        return False

    if not _image_exists_and_valid():
        _fail("Image built but did not pass ODA runtime label validation.")
        return False

    _ok("Image built and validated.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up the ODA sandbox Docker image.")
    parser.add_argument(
        "--source",
        choices=["local", "registry", "auto"],
        default=None,
        help="Image source: local=build only, registry=pull only, auto=pull then build.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-pull or rebuild even if a valid image already exists locally.",
    )
    args = parser.parse_args()

    source = args.source or _cfg("SANDBOX_IMAGE_SOURCE", "auto")
    if source not in {"local", "registry", "auto"}:
        source = "auto"

    print("\nODA sandbox image setup", flush=True)
    print(f"  image  : {SANDBOX_IMAGE}", flush=True)
    print(f"  source : {source}", flush=True)
    print(flush=True)

    print("Checking Docker...", flush=True)
    if not _check_docker() or not _check_daemon():
        return 1
    print(flush=True)

    if not args.force and _image_exists_and_valid():
        _ok(f"Image '{SANDBOX_IMAGE}' already present and valid. Nothing to do.")
        print(flush=True)
        return 0

    if args.force:
        _info("--force: skipping existing image check.")

    print("Fetching image...", flush=True)
    if source == "local":
        success = _build() or _pull()
    elif source == "registry":
        success = _pull() or _build()
    else:
        success = _pull() or _build()

    print(flush=True)
    if success:
        print("Setup complete. You can now start ODA sandbox.", flush=True)
        return 0

    print("Setup failed. See errors above.", file=sys.stderr, flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
