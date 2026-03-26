# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SERVER_ROOT = Path(__file__).resolve().parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

MCP_SERVER = {
    "id": "deep_think",
    "name": "Deep Think",
    "description": "Long-form reasoning and research synthesis.",
}

TOOLS = [
    {
        "id": "deep_think",
        "name": "Deep Think",
        "description": (
            "Launch the Deep Think multi-agent research swarm on a question or task. "
            "A coordinator spawns specialist sub-agents that iterate through reflect, search, python, and finish cycles. "
            "Returns a structured Markdown report with findings, reasoning trace, and source references saved to _out/<task_id>/. "
            "mode='full' produces a comprehensive report with all sub-agent findings included. "
            "mode='quick' runs a single fast pass — suitable for quick factual lookups. "
            "WARNING: full mode can take several minutes. Do not interrupt — wait for the report."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Research question or task for the Deep Think orchestrator.",
                },
                "mode": {
                    "type": "string",
                    "description": "Run mode: 'full' for full report, 'quick' for a shorter pass.",
                    "enum": ["full", "quick"],
                    "default": "full",
                },
            },
            "required": ["query"],
        },
    }
]


def supports(engine: str | None = None, model_name: str | None = None) -> bool:
    """Expose this tool server only for Ollama tool-calling flows."""

    return engine == "ollama-service"


async def _run_with_optional_keepalive(coro, session=None, interval: float = 10.0):
    """Run a coroutine while optionally sending debug keepalives to an MCP session."""

    if session is None:
        return await coro

    result = None
    done = asyncio.Event()

    async def _ping_loop() -> None:
        while not done.is_set():
            try:
                await asyncio.wait_for(asyncio.shield(done.wait()), timeout=interval)
            except asyncio.TimeoutError:
                pass

            if done.is_set():
                continue

            try:
                await session.send_log_message(level="debug", data="thinking...", logger="deep-think")
            except Exception:
                pass

    async def _run() -> None:
        nonlocal result
        result = await coro
        done.set()

    await asyncio.gather(_run(), _ping_loop())
    return result


async def _deep_think(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> str:
    """Run Deep Think and return a model-friendly report."""

    from src.orchestrator import orchestrator
    from src.llm_client import llm_client

    query = str((arguments or {}).get("query", "")).strip()
    if not query:
        return "Deep Think Error: query is required."

    normalized_mode = "quick" if str((arguments or {}).get("mode", "full")).lower() == "quick" else "full"
    runtime_context = dict(context or {})
    runtime_engine = str(runtime_context.get("engine") or "ollama-service").strip()
    runtime_model = str(runtime_context.get("model_name") or "").strip()
    logger.info("Deep Think started: %s... (mode=%s)", query[:100], normalized_mode)

    session = runtime_context.get("mcp_session")

    try:
        with llm_client.runtime_target(engine=runtime_engine, model_name=runtime_model):
            report = await _run_with_optional_keepalive(
                orchestrator.run(query=query, mode=normalized_mode),
                session=session,
            )
        formatted = orchestrator.format_report_for_llm(
            report,
            include_raw_reports=normalized_mode == "full",
        )
        logger.info("Deep Think completed successfully (%s)", report.task_id)
        return formatted
    except Exception as exc:
        logger.exception("Deep Think failed")
        return f"Deep Think Error: {exc}"


TOOL_HANDLERS = {
    "deep_think": _deep_think,
}


def register_tools(mcp) -> None:
    """Attach Deep Think tools to the provided MCP server."""

    @mcp.tool()
    async def deep_think(query: str, mode: str = "full") -> str:
        """Launch the Deep Think multi-agent research swarm on a question or task. A coordinator spawns specialist sub-agents that iterate through reflect, search, python, and finish cycles. Returns a structured Markdown report with findings, reasoning trace, and source references saved to _out/<task_id>/. mode='full' produces a comprehensive report with all sub-agent findings included. mode='quick' runs a single fast pass suitable for quick factual lookups. WARNING: full mode can take several minutes — wait for completion."""

        session = None
        try:
            session = mcp._mcp_server.request_context.session
        except Exception:
            session = None

        return await _deep_think(
            {"query": query, "mode": mode},
            {"mcp_session": session},
        )
