# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("core.fetch.shopping.worker")

_WORKER_SCRIPT = Path(__file__).resolve().parents[1] / "_shopping_worker.py"


def _read_partial_result(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        target = Path(path)
        if not target.exists():
            return {}
        payload = json.loads(target.read_text(encoding="utf-8"))
        result = payload.get("result") or {}
        if isinstance(result, dict):
            result["partial"] = True
            result["partial_reason"] = result.get("partial_reason") or "worker_timeout"
            return result
    except Exception as exc:
        logger.debug("shopping partial buffer read failed path=%r err=%s", path, exc)
    return {}


def _empty_result(query: str, effort: str, reason: str) -> dict[str, Any]:
    return {
        "query": query,
        "effort": effort,
        "mix": {},
        "products": [],
        "attempts": [],
        "provider_state": {},
        "timings": {},
        "partial": bool(reason),
        "partial_reason": reason,
    }


async def async_shopping_search_worker(
    query: str,
    *,
    effort: str = "medium",
    limit: int = 8,
    worker_timeout: float | None = None,
) -> dict[str, Any]:
    timeout = float(worker_timeout if worker_timeout is not None else 8.0)
    request_payload = {
        "query": query,
        "effort": effort,
        "limit": max(1, int(limit)),
    }

    partial_buffer_path: str | None = None
    with tempfile.NamedTemporaryFile(
        prefix="shopping_partial_",
        suffix=".json",
        delete=False,
    ) as partial_buffer:
        partial_buffer_path = partial_buffer.name
    request_payload["partial_buffer_path"] = partial_buffer_path

    proc: asyncio.subprocess.Process | None = None
    stdout: bytes | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-u",
            str(_WORKER_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(
            proc.communicate(json.dumps(request_payload, ensure_ascii=False).encode("utf-8")),
            timeout=max(0.1, timeout),
        )
    except asyncio.TimeoutError:
        partial = _read_partial_result(partial_buffer_path)
        if partial:
            logger.warning("shopping worker timeout after %.1fs for query=%r; returning partial", timeout, query[:96])
            return partial
        logger.warning("shopping worker timeout after %.1fs for query=%r", timeout, query[:96])
        return _empty_result(query, effort, "worker_timeout")
    except asyncio.CancelledError:
        logger.debug("shopping worker cancelled for query=%r", query[:96])
        raise
    except Exception as exc:
        logger.warning("shopping worker error for query=%r: %s", query[:96], exc)
        return _empty_result(query, effort, f"worker_error:{type(exc).__name__}")
    finally:
        if proc is not None and proc.returncode is None:
            with contextlib.suppress(Exception):
                proc.kill()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(proc.wait(), timeout=3.0)
        if partial_buffer_path:
            with contextlib.suppress(Exception):
                Path(partial_buffer_path).unlink()
            with contextlib.suppress(Exception):
                Path(partial_buffer_path + ".tmp").unlink()

    if proc is not None and proc.returncode not in (0, None):
        partial = _read_partial_result(partial_buffer_path)
        if partial:
            return partial
        logger.warning("shopping worker exited code %s for query=%r", proc.returncode, query[:96])
        return _empty_result(query, effort, "worker_exit")

    stdout_text = (stdout or b"").decode("utf-8", errors="replace").strip()
    if not stdout_text:
        return _empty_result(query, effort, "worker_empty_stdout")
    try:
        payload = json.loads(stdout_text)
    except Exception as exc:
        logger.warning("shopping worker invalid JSON for query=%r: %s", query[:96], exc)
        return _empty_result(query, effort, "worker_invalid_json")
    if not payload.get("ok", False):
        return _empty_result(query, effort, str(payload.get("error") or "worker_failed"))
    result = payload.get("result") or {}
    return result if isinstance(result, dict) else _empty_result(query, effort, "worker_bad_result")
