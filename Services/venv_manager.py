# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = BASE_DIR / "Settings" / "venv_requirements.json"
STATE_FILE_NAME = ".aslm_venv_state.json"
ACTIVE_VENV_ENV = "ASLM_CHAT_ACTIVE_VENV"
MANAGED_VENVS_ROOT = BASE_DIR / "Data" / "venvs"


PACKAGE_VALIDATION_CODE = r"""
import importlib.metadata as metadata
import json
import sys

try:
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.utils import canonicalize_name
except Exception as exc:
    print(json.dumps({"failures": [{"package": "pip", "reason": "pip packaging helpers are unavailable", "details": str(exc)}]}))
    raise SystemExit(1)

requirements = json.loads(sys.argv[1])
installed = {}
for distribution in metadata.distributions():
    name = distribution.metadata.get("Name")
    if name:
        installed[canonicalize_name(name)] = distribution.version

failures = []
for raw_requirement in requirements:
    try:
        requirement = Requirement(raw_requirement)
    except Exception as exc:
        failures.append({"package": raw_requirement, "reason": "invalid requirement", "details": str(exc)})
        continue

    if requirement.marker is not None and not requirement.marker.evaluate():
        continue

    package_name = canonicalize_name(requirement.name)
    installed_version = installed.get(package_name)
    if installed_version is None:
        failures.append({"package": requirement.name, "required": str(requirement.specifier), "reason": "missing"})
        continue

    if requirement.specifier and not requirement.specifier.contains(installed_version, prereleases=True):
        failures.append(
            {
                "package": requirement.name,
                "required": str(requirement.specifier),
                "installed": installed_version,
                "reason": "version mismatch",
            }
        )

print(json.dumps({"failures": failures}))
raise SystemExit(1 if failures else 0)
"""


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

        venvs.append(
            {
                "id": venv_id,
                "path": relative_path,
                "tool": str(raw_item.get("tool", "") or "").strip(),
                "packages": [str(package).strip() for package in packages if str(package).strip()],
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


# Run one subprocess command and return captured output.
def _run_capture(command: list[str], *, cwd: Path | None = None) -> tuple[bool, str, str]:
    """Run one command while capturing stdout and stderr."""

    try:
        result = subprocess.run(
            command,
            cwd=str(cwd or BASE_DIR),
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception as exc:
        return False, "", str(exc)

    return result.returncode == 0, result.stdout or "", result.stderr or ""


# Compute a dependency signature.
def _packages_signature(packages: list[str]) -> str:
    """Return a stable signature for one package list."""

    payload = json.dumps(packages, ensure_ascii=True, sort_keys=True)
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
def _write_state(venv_path: Path, packages: list[str]) -> None:
    """Persist the package signature for one venv."""

    state_path = venv_path / STATE_FILE_NAME
    payload = {
        "packagesHash": _packages_signature(packages),
        "packageCount": len(packages),
    }
    state_path.write_text(json.dumps(payload, indent=4, ensure_ascii=False), encoding="utf-8")


# Return whether a venv path belongs to ASLM-Chat's managed venv root.
def _is_managed_venv_path(venv_path: Path) -> bool:
    """Return whether the venv path is safe for automatic replacement."""

    try:
        root = os.path.normcase(str(MANAGED_VENVS_ROOT.resolve(strict=False)))
        candidate = os.path.normcase(str(venv_path.resolve(strict=False)))
        return os.path.commonpath([root, candidate]) == root
    except (OSError, ValueError):
        return False


# Clear read-only attributes while deleting a venv on Windows.
def _handle_remove_readonly(remove_func: Any, path: str, _: Any) -> None:
    """Retry one failed delete after making the path writable."""

    os.chmod(path, stat.S_IWRITE)
    remove_func(path)


# Remove one managed venv before a clean reinstall.
def _remove_venv(venv_id: str, reason: str, log: bool) -> bool:
    """Delete one configured ASLM-Chat venv when it must be recreated."""

    venv_path = get_venv_path(venv_id)
    if not venv_path.exists():
        return True

    if not _is_managed_venv_path(venv_path):
        if log:
            print(f"[ASLM-Chat] Refusing to remove venv '{venv_id}' outside managed root: {venv_path}")
        return False

    if log:
        print(f"[ASLM-Chat] Removing venv '{venv_id}' ({reason}).")

    try:
        shutil.rmtree(venv_path, onerror=_handle_remove_readonly)
    except OSError as exc:
        if log:
            print(f"[ASLM-Chat] Could not remove venv '{venv_id}': {exc}")
        return False

    return True


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
def _install_packages(venv_id: str, packages: list[str], log: bool) -> bool:
    """Install the configured packages into one venv."""

    if not packages:
        return True

    python_path = get_venv_python(venv_id)
    if not python_path.exists():
        return False

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".txt") as requirements_file:
        requirements_file.write("\n".join(packages))
        requirements_file.write("\n")
        requirements_path = requirements_file.name

    try:
        if log:
            print(f"[ASLM-Chat] Installing {len(packages)} package(s) into venv '{venv_id}'")

        return _run(
            [
                str(python_path),
                "-m",
                "pip",
                "install",
                "--no-warn-script-location",
                "-r",
                requirements_path,
            ],
            log=log,
        )
    finally:
        try:
            Path(requirements_path).unlink(missing_ok=True)
        except OSError:
            pass


# Check that the venv Python executable can run.
def _validate_python(venv_id: str) -> tuple[bool, str]:
    """Return whether the Python executable inside one venv is usable."""

    python_path = get_venv_python(venv_id)
    if not python_path.exists():
        return False, "missing python executable"

    ok, _, stderr = _run_capture([str(python_path), "-c", "import sys; print(sys.version)"])
    if not ok:
        details = stderr.strip()
        return False, f"broken python executable: {details}" if details else "broken python executable"

    return True, ""


# Check that configured packages are present with compatible versions.
def _validate_installed_packages(venv_id: str, packages: list[str]) -> tuple[bool, str]:
    """Return whether one venv satisfies the configured package requirements."""

    if not packages:
        return True, ""

    python_path = get_venv_python(venv_id)
    requirements_json = json.dumps(packages, ensure_ascii=True)
    ok, stdout, stderr = _run_capture([str(python_path), "-c", PACKAGE_VALIDATION_CODE, requirements_json])
    output = (stdout or "").strip()

    try:
        payload = json.loads(output or "{}")
    except json.JSONDecodeError:
        details = (stderr or output).strip()
        return False, f"package validation failed: {details}" if details else "package validation failed"

    failures = payload.get("failures", [])
    if ok and not failures:
        return True, ""

    if isinstance(failures, list) and failures:
        first_failure = failures[0] if isinstance(failures[0], dict) else {"reason": str(failures[0])}
        package = first_failure.get("package", "unknown package")
        reason = first_failure.get("reason", "invalid package state")
        installed = first_failure.get("installed")
        required = first_failure.get("required")
        suffix = ""
        if installed or required:
            suffix = f" (installed: {installed or 'missing'}, required: {required or 'any'})"
        extra = f"; {len(failures) - 1} more issue(s)" if len(failures) > 1 else ""
        return False, f"{package}: {reason}{suffix}{extra}"

    details = stderr.strip()
    return False, f"package validation failed: {details}" if details else "package validation failed"


# Check that installed distributions have compatible dependencies.
def _validate_pip_check(venv_id: str) -> tuple[bool, str]:
    """Return whether pip sees a consistent dependency graph inside one venv."""

    python_path = get_venv_python(venv_id)
    ok, stdout, stderr = _run_capture([str(python_path), "-m", "pip", "check"])
    if ok:
        return True, ""

    details = (stdout or stderr).strip()
    return False, f"pip check failed: {details}" if details else "pip check failed"


# Validate one complete venv.
def _validate_venv(venv_id: str, packages: list[str]) -> tuple[bool, str]:
    """Return whether one venv is usable and satisfies its configured packages."""

    checks = (
        _validate_python,
        lambda current_venv_id: _validate_installed_packages(current_venv_id, packages),
        _validate_pip_check,
    )

    for check in checks:
        ok, reason = check(venv_id)
        if not ok:
            return False, reason

    return True, ""


# Recreate one venv from scratch and persist its dependency state.
def _recreate_venv(venv_id: str, packages: list[str], reason: str, log: bool) -> bool:
    """Remove, create, install, validate, and persist one ASLM-Chat venv."""

    if not _remove_venv(venv_id, reason, log):
        return False

    if not _create_venv(venv_id, log):
        return False

    if not _install_packages(venv_id, packages, log):
        return False

    valid, validation_reason = _validate_venv(venv_id, packages)
    if not valid:
        if log:
            print(f"[ASLM-Chat] Venv '{venv_id}' validation failed after install: {validation_reason}")
        return False

    _write_state(get_venv_path(venv_id), packages)
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
    packages_hash = _packages_signature(packages)

    if not python_path.exists():
        reason = "missing python executable" if venv_path.exists() else "missing venv"
        return _recreate_venv(venv_id, packages, reason, log)

    state = _read_state(venv_path)
    state_hash = state.get("packagesHash")
    if isinstance(state_hash, str) and state_hash and state_hash != packages_hash:
        return _recreate_venv(venv_id, packages, "requirements changed", log)

    valid, validation_reason = _validate_venv(venv_id, packages)
    if valid:
        if state_hash != packages_hash:
            _write_state(venv_path, packages)
        if log:
            print(f"[ASLM-Chat] Venv '{venv_id}' is up to date.")
        return True

    return _recreate_venv(venv_id, packages, validation_reason, log)


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
