# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
HOST_LOCALE_FILE = BASE_DIR / "Settings" / "host_locale.json"


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON to ``path`` using replace-on-success semantics."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
            file.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def save_host_locale_payload(data: dict[str, Any]) -> None:
    """Persist the ASLM host locale snapshot next to module settings."""

    if not isinstance(data, dict):
        raise TypeError("host locale payload must be a dict")
    atomic_write_json(HOST_LOCALE_FILE, data)


def load_host_locale() -> dict[str, Any] | None:
    """Return the last persisted host locale snapshot, or None if missing or invalid."""

    if not HOST_LOCALE_FILE.exists():
        return None
    try:
        text = HOST_LOCALE_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read host locale file %s: %s", HOST_LOCALE_FILE, exc)
        return None
    text = text.lstrip("\ufeff").strip()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Could not parse host locale file %s: %s", HOST_LOCALE_FILE, exc)
        return None
    return raw if isinstance(raw, dict) else None
