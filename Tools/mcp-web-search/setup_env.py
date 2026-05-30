# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]


# Ensure the ASLM-Chat managed venv for this tool exists and is up to date.
def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create or update the mcp-web-search venv defined in "
            "Settings/venv_requirements.json (ASLM-Chat venv_manager)."
        )
    )
    parser.add_argument(
        "--pytest",
        action="store_true",
        help="Install pytest into the tool venv for local test runs.",
    )
    args = parser.parse_args()

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from Services import venv_manager

    if not venv_manager.ensure_venv("mcp-web-search", log=True):
        return 1

    python_path = venv_manager.get_venv_python("mcp-web-search")
    if args.pytest:
        subprocess.run([str(python_path), "-m", "pip", "install", "pytest"], check=True)

    print(f"Venv : {venv_manager.get_venv_path('mcp-web-search')}")
    print(f"Python: {python_path}")
    print(
        "Tests: cd Tools/mcp-web-search && "
        f'"{python_path}" -m pytest -q -m "not gliner and not integration and not live"'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
