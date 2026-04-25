#!/usr/bin/env python3
"""Bootstrap a local virtualenv and install dependencies from pyproject.toml."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PYPROJECT = ROOT / "pyproject.toml"


def _load_project_name() -> str:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return str(data.get("project", {}).get("name", ROOT.name))


def _venv_python(venv_dir: Path) -> Path:
    if sys.platform.startswith("win"):
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _run(cmd: list[str], *, cwd: Path) -> None:
    print(">", " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd), check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a venv and install this project from pyproject.toml."
    )
    parser.add_argument(
        "--venv",
        default=".venv",
        help="Virtual environment directory relative to the project root. Default: .venv",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Base Python executable used to create the venv. Default: current interpreter",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Install optional dev dependencies too (equivalent to .[dev]).",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the virtual environment before installing.",
    )
    args = parser.parse_args()

    if not PYPROJECT.exists():
        raise SystemExit(f"pyproject.toml not found at {PYPROJECT}")

    project_name = _load_project_name()
    venv_dir = (ROOT / args.venv).resolve()

    if args.recreate and venv_dir.exists():
        import shutil

        print(f"Removing existing virtualenv: {venv_dir}")
        shutil.rmtree(venv_dir)

    if not venv_dir.exists():
        _run([args.python, "-m", "venv", str(venv_dir)], cwd=ROOT)

    venv_python = _venv_python(venv_dir)
    if not venv_python.exists():
        raise SystemExit(f"Virtualenv Python not found: {venv_python}")

    spec = ".[dev]" if args.dev else "."

    print(f"Project : {project_name}")
    print(f"Root    : {ROOT}")
    print(f"Venv    : {venv_dir}")
    print(f"Python  : {venv_python}")
    print(f"Install : {spec}")
    print()

    _run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], cwd=ROOT)
    _run([str(venv_python), "-m", "pip", "install", "-e", spec], cwd=ROOT)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
