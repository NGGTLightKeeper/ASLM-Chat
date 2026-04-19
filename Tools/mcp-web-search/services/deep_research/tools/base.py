# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Shared helpers for deep research tools."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from services.deep_research.models import ToolTrace


def summarize_text(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 15)].rstrip() + " ...[truncated]"


async def traced_tool_call(
    *,
    step: int,
    action: str,
    payload: dict[str, Any],
    runner: Callable[[], Any],
) -> tuple[str, Any, ToolTrace]:
    start = time.time()
    try:
        result = await runner()
        summary = summarize_text(str(result), 700)
        trace = ToolTrace(
            step=step,
            action=action,
            input=payload,
            status="success",
            output_summary=summary,
            elapsed_ms=int((time.time() - start) * 1000),
        )
        return "success", result, trace
    except Exception as exc:
        trace = ToolTrace(
            step=step,
            action=action,
            input=payload,
            status="error",
            output_summary=f"{type(exc).__name__}: {exc}",
            elapsed_ms=int((time.time() - start) * 1000),
        )
        return "error", None, trace
