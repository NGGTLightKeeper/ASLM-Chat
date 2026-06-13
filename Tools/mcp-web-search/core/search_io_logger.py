# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

# Ported from the legacy adapters/mcp/search_io_logger.py: appends each full
# search / read_page tool IO event to a single readable JSON array, so the exact
# request and response the model saw can be inspected after the fact. Diagnostics
# only — it must never break the tool call itself.

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOG_LOCK = threading.Lock()
_LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "model_search_io.json"


# Coerce a value to something JSON-serializable for the IO log.
def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False, default=str)
        return value
    except Exception:
        return repr(value)


# Drop redundant preview fields when they duplicate the snippet text.
def _without_duplicate_preview(value: Any) -> Any:
    if isinstance(value, list):
        return [_without_duplicate_preview(item) for item in value]
    if not isinstance(value, dict):
        return value

    cleaned = {key: _without_duplicate_preview(item) for key, item in value.items()}
    snippet = cleaned.get("snippet")
    preview = cleaned.get("preview")
    if isinstance(snippet, str) and isinstance(preview, str) and snippet == preview:
        cleaned.pop("preview", None)
    return cleaned


# Append one full search/read-page IO event to a readable JSON array.
def write_search_io_event(event: dict[str, Any]) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **dict(event or {}),
    }
    record = _without_duplicate_preview(record)
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_LOCK:
            entries: list[Any] = []
            if _LOG_PATH.exists():
                try:
                    loaded = json.loads(_LOG_PATH.read_text(encoding="utf-8") or "[]")
                    if isinstance(loaded, list):
                        entries = loaded
                except Exception:
                    entries = []
            entries.append(_jsonable(record))
            _LOG_PATH.write_text(
                json.dumps(entries, ensure_ascii=False, default=str, indent=2),
                encoding="utf-8",
            )
    except Exception:
        # Diagnostics must never break search itself.
        return
