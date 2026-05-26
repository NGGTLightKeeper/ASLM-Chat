# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = BASE_DIR / "Settings" / "venv_requirements.json"
STATE_FILE_NAME = ".aslm_venv_state.json"
ACTIVE_VENV_ENV = "ASLM_CHAT_ACTIVE_VENV"


# Read venv requirements configuration.
def load_config() -> dict[str, Any]:
    """Return the internal venv configuration."""

    if not REQUIREMENTS_FILE.exists():
        return {"fileVersion": 1, "venvs": []}

    try:
        payload = json.loads(REQUIREMENTS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"fileVersion": 1, "venvs": []}

    return payload if isinstance(payload, dict) else {"fileVersion": 1, "venvs": []}


# Return normalized venv definitions.
def iter_venv_configs() -> list[dict[str, Any]]:
    """Return valid venv entries from the requirements configuration."""

    raw_venvs = load_config().get("venvs", [])
    if not isinstance(raw_venvs, list):
        return []

    venvs: list[dict[str, Any]] = []
    for raw_item in raw_venvs:
        if not isinstance(raw_item, dict):
            continue

        venv_id = str(raw_item.get("id", "") or "").strip()
        relative_path = str(raw_item.get("path", "") or "").strip()
        if not venv_id or not relative_path:
            continue

        packages = raw_item.get("packages", [])
        if not isinstance(packages, list):
            packages = []
        packages_no_deps = raw_item.get("packagesNoDeps", [])
        if not isinstance(packages_no_deps, list):
            packages_no_deps = []

        venvs.append(
            {
                "id": venv_id,
                "path": relative_path,
                "tool": str(raw_item.get("tool", "") or "").strip(),
                "packages": [str(package).strip() for package in packages if str(package).strip()],
                "packages_no_deps": [
                    str(package).strip() for package in packages_no_deps if str(package).strip()
                ],
            }
        )

    return venvs


# Resolve one venv config by id.
def get_venv_config(venv_id: str) -> dict[str, Any] | None:
    """Return one venv config by id."""

    normalized_id = str(venv_id or "").strip()
    for config in iter_venv_configs():
        if config["id"] == normalized_id:
            return config
    return None


# Resolve one tool directory to its venv id.
def get_tool_venv_id(tool_dir_name: str) -> str:
    """Return the venv id assigned to a tool directory."""

    normalized_name = str(tool_dir_name or "").strip()
    for config in iter_venv_configs():
        if config.get("tool") == normalized_name:
            return str(config["id"])
    return ""


# Return the absolute venv path.
def get_venv_path(venv_id: str) -> Path:
    """Return the absolute path for a configured venv."""

    config = get_venv_config(venv_id)
    if config is None:
        raise KeyError(f"Unknown ASLM-Chat venv: {venv_id}")

    path = Path(config["path"])
    return path if path.is_absolute() else BASE_DIR / path


# Return the Python executable inside a venv.
def get_venv_python(venv_id: str) -> Path:
    """Return the Python executable for a configured venv."""

    venv_path = get_venv_path(venv_id)
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    executable_name = "python.exe" if os.name == "nt" else "python"
    return venv_path / scripts_dir / executable_name


# Return the Python executable for a tool venv when configured.
def get_tool_python(tool_dir_name: str) -> Path | None:
    """Return the Python executable assigned to a tool directory."""

    venv_id = get_tool_venv_id(tool_dir_name)
    if not venv_id:
        return None

    python_path = get_venv_python(venv_id)
    return python_path if python_path.exists() else None


# Run one subprocess command.
def _run(command: list[str], *, log: bool, cwd: Path | None = None) -> bool:
    """Run one command and optionally stream output to the console."""

    try:
        result = subprocess.run(
            command,
            cwd=str(cwd or BASE_DIR),
            text=True,
            capture_output=not log,
            check=False,
        )
    except Exception as exc:
        if log:
            print(f"[ASLM-Chat] Command could not be started: {exc}")
        return False

    if log and result.returncode != 0:
        print(f"[ASLM-Chat] Command failed with exit code {result.returncode}: {' '.join(command)}")

    return result.returncode == 0


# Compute a dependency signature.
def _packages_signature(packages: list[str], packages_no_deps: list[str] | None = None) -> str:
    """Return a stable signature for one venv package manifest."""

    payload = json.dumps(
        {"packages": packages, "packagesNoDeps": packages_no_deps or []},
        ensure_ascii=True,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# Read the stored venv state.
def _read_state(venv_path: Path) -> dict[str, Any]:
    """Return persisted state for one venv."""

    state_path = venv_path / STATE_FILE_NAME
    if not state_path.exists():
        return {}

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    return payload if isinstance(payload, dict) else {}


# Write the stored venv state.
def _write_state(venv_path: Path, packages: list[str], packages_no_deps: list[str] | None = None) -> None:
    """Persist the package signature for one venv."""

    state_path = venv_path / STATE_FILE_NAME
    no_deps = packages_no_deps or []
    payload = {
        "packagesHash": _packages_signature(packages, no_deps),
        "packageCount": len(packages) + len(no_deps),
    }
    state_path.write_text(json.dumps(payload, indent=4, ensure_ascii=False), encoding="utf-8")


# Create a virtual environment.
def _create_venv(venv_id: str, log: bool) -> bool:
    """Create a Python virtual environment for one ASLM-Chat part."""

    venv_path = get_venv_path(venv_id)
    venv_path.parent.mkdir(parents=True, exist_ok=True)

    if log:
        print(f"[ASLM-Chat] Creating venv '{venv_id}' at {venv_path}")

    if importlib.util.find_spec("venv") is not None and _run([sys.executable, "-m", "venv", str(venv_path)], log=log):
        return True

    # Some embeddable Python runtimes do not ship the stdlib venv module.
    _run([sys.executable, "-m", "pip", "install", "--no-warn-script-location", "virtualenv"], log=log)
    return _run([sys.executable, "-m", "virtualenv", str(venv_path)], log=log)


# Install packages into one venv.
def _pip_install(
    python_path: Path,
    packages: list[str],
    *,
    no_deps: bool,
    log: bool,
    label: str,
) -> bool:
    if not packages:
        return True

    command = [
        str(python_path),
        "-m",
        "pip",
        "install",
        "--no-warn-script-location",
    ]
    if no_deps:
        command.append("--no-deps")
    command.extend(packages)

    if log:
        suffix = " (no deps)" if no_deps else ""
        print(f"[ASLM-Chat] Installing {len(packages)} package(s){suffix} into venv '{label}'")

    return _run(command, log=log)


def _install_packages(
    venv_id: str,
    packages: list[str],
    packages_no_deps: list[str],
    log: bool,
) -> bool:
    """Install the configured packages into one venv."""

    if not packages and not packages_no_deps:
        return True

    python_path = get_venv_python(venv_id)
    if not python_path.exists():
        return False

    if packages and not _pip_install(python_path, packages, no_deps=False, log=log, label=venv_id):
        return False

    if packages_no_deps and not _pip_install(
        python_path, packages_no_deps, no_deps=True, log=log, label=venv_id
    ):
        return False

    return True


# Ensure one configured venv exists and has its packages.
def ensure_venv(venv_id: str, *, log: bool = True) -> bool:
    """Create or update one internal ASLM-Chat venv."""

    config = get_venv_config(venv_id)
    if config is None:
        if log:
            print(f"[ASLM-Chat] Unknown venv '{venv_id}'.")
        return False

    venv_path = get_venv_path(venv_id)
    python_path = get_venv_python(venv_id)
    packages = list(config.get("packages", []))
    packages_no_deps = list(config.get("packages_no_deps", []))

    if not python_path.exists() and not _create_venv(venv_id, log):
        return False

    state = _read_state(venv_path)
    if state.get("packagesHash") == _packages_signature(packages, packages_no_deps):
        if log:
            print(f"[ASLM-Chat] Venv '{venv_id}' is up to date.")
        return True

    if not _install_packages(venv_id, packages, packages_no_deps, log):
        return False

    _write_state(venv_path, packages, packages_no_deps)
    return True


# Ensure all configured venvs.
def ensure_all(*, log: bool = True) -> bool:
    """Create or update every configured ASLM-Chat venv."""

    ok = True
    for config in iter_venv_configs():
        ok = ensure_venv(str(config["id"]), log=log) and ok
    return ok


# Run a Python command inside one configured venv.
def run_venv_python(venv_id: str, args: list[str], *, log: bool = True) -> bool:
    """Run a Python command inside one configured venv."""

    if not ensure_venv(venv_id, log=log):
        return False

    return _run([str(get_venv_python(venv_id)), *args], log=log)


# Run a Python code snippet inside one configured venv.
def run_venv_code(venv_id: str, code: str, *, log: bool = True) -> bool:
    """Run Python code inside one configured venv."""

    return run_venv_python(venv_id, ["-c", code], log=log)
