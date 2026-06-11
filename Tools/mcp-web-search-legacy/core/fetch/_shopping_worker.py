# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
from pathlib import Path

# Force UTF-8 stdout so JSON with non-ASCII is transmitted cleanly.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Make core/ importable when run as a script from any working directory.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _fail(msg: str) -> None:
    sys.stdout.write(json.dumps({"ok": False, "error": msg}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _write_partial(path: str | None, result: dict) -> None:
    if not path or not result.get("products"):
        return
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        payload = {"ok": True, "partial": True, "result": result}
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)
    except Exception:
        pass


async def _run(payload: dict) -> dict:
    from core.fetch.shopping.engine import result_to_jsonable, search_shopping

    query = str(payload.get("query") or "").strip()
    if not query:
        raise ValueError("empty query")
    effort = str(payload.get("effort") or "medium")
    limit = max(1, int(payload.get("limit") or 8))
    language = str(payload.get("language") or "en")
    result = await search_shopping(query, effort=effort, limit=limit, language=language)
    return result_to_jsonable(result)


def main() -> None:
    try:
        raw = sys.stdin.buffer.read()
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as exc:
        _fail(f"bad stdin: {exc}")
        os._exit(1)

    partial_buffer_path = payload.get("partial_buffer_path")
    try:
        result = asyncio.run(_run(payload))
        _write_partial(partial_buffer_path, result)
        sys.stdout.write(json.dumps({"ok": True, "result": result}, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        os._exit(0)
    except Exception as exc:
        _fail(f"shopping worker error: {exc}")
        os._exit(1)


if __name__ == "__main__":
    main()
