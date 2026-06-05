# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from .settings import BASE_DIR


# Load the local module manifest when it exists and is valid JSON.
def _load_module_manifest() -> dict[str, Any] | None:
    json_path = BASE_DIR / "ASLM_Module.json"
    if not json_path.exists():
        return None

    try:
        with json_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return None

    return data if isinstance(data, dict) else None


# Print a standard separator line for console output.
def _print_separator() -> None:
    print("------------------------------------------------------")


# Print module metadata and startup time to the console.
class PrintTechData:
    # Print module manifest details and the current startup timestamp.
    def PTD_Print(self) -> None:
        _print_separator()

        # Read and print module manifest details when available.
        data = _load_module_manifest()
        if data is None:
            print("Error reading config")
        else:
            source = data.get("source") if isinstance(data.get("source"), dict) else {}

            print(
                f"Module: {data.get('name', 'N/A')}, "
                f"v{data.get('version', 'N/A')} by {data.get('author', 'N/A')}"
            )
            print(
                f"ID: {data.get('id', 'N/A')} | "
                f"Type: {data.get('type', 'N/A')} | "
                f"HasPage: {data.get('hasPage', 'N/A')}"
            )

            if source.get("type") == "github":
                print(f"SourceCode: https://github.com/{source.get('repo', '')}")

        _print_separator()

        # Print the current module start time separately from manifest data.
        started_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Module Start Time: {started_at}")

        _print_separator()
