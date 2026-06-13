# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

SERVER_ROOT = Path(__file__).resolve().parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from core.logging_setup import setup_logging
from core.search.serp_api import run_serp_search
from core.search.web_search import run_web_search
from core.search_io_logger import write_search_io_event

# Wire rotating file logs (web_search.log / read_page.log / core.log / mcp_trace.log)
# and the model IO log before anything runs, exactly like the legacy adapter.
setup_logging()
logger = logging.getLogger("mcp.server")

_VALID_EFFORTS = frozenset({"low", "medium", "high"})

MCP_SERVER = {
    "id": "web_search",
    "name": "Web Search",
    "description": "Web search for the model: ranked multi-engine results with optional page parsing.",
}

TOOLS = [
    {
        "id": "web_search",
        "name": "Web Search",
        "description": (
            "Primary search tool. Runs Google, Brave, DuckDuckGo, Yandex, Qwant, Yep and "
            "Startpage in parallel, deduplicates by cross-engine consensus, ranks the pool, "
            "and (medium/high effort) parses the best pages into markdown. effort: 'low' = "
            "fast SERP-only, 'medium' = parse a few winners, 'high' = deep parse + max recall."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "effort": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "default": "medium",
                },
                "region": {"type": "string", "default": ""},
                "safesearch": {
                    "type": "string",
                    "enum": ["on", "moderate", "off"],
                    "default": "moderate",
                },
                "timelimit": {"type": "string", "enum": ["d", "w", "m", "y"]},
            },
            "required": ["query"],
        },
    },
    {
        "id": "serp_search",
        "name": "SERP Search (raw)",
        "description": (
            "Low-level raw SERP retrieval (no triage/ranking/parsing) from the same engines. "
            "Use web_search instead unless you need the unprocessed per-engine output."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "region": {"type": "string", "default": "us-en"},
                "safesearch": {
                    "type": "string",
                    "enum": ["on", "moderate", "off"],
                    "default": "moderate",
                },
                "timelimit": {"type": "string", "enum": ["d", "w", "m", "y"]},
                "timeout_seconds": {"type": "number", "default": 8.0},
            },
            "required": ["query"],
        },
    },
]


# Return whether this server supports the given engine or model.
def supports(engine: str | None = None, model_name: str | None = None) -> bool:
    return engine in (None, "ollama-service", "lms", "openai", "google-genai")


# Run the ranked web_search pipeline (the model-facing default tool).
async def _call_web_search(args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    effort = str(args.get("effort") or "medium").lower()
    if effort not in _VALID_EFFORTS:
        effort = "medium"
    region = str(args.get("region") or "")
    safesearch = str(args.get("safesearch") or "moderate")
    timelimit = str(args["timelimit"]) if args.get("timelimit") else None

    write_search_io_event(
        {
            "layer": "mcp_adapter",
            "phase": "web_search.request",
            "tool_id": "web_search",
            "query": query,
            "effort": effort,
            "region": region,
        }
    )
    logger.info("mcp.web_search.start effort=%s query_preview=%r", effort, query[:160])
    started = time.perf_counter()
    try:
        result = await run_web_search(
            query, effort=effort, region=region, safesearch=safesearch, timelimit=timelimit
        )
    except Exception:
        logger.exception("mcp.web_search.failed query_preview=%r", query[:160])
        raise
    elapsed = time.perf_counter() - started
    logger.info(
        "mcp.web_search.done effort=%s sources=%d elapsed=%.3fs",
        effort, len(result.get("sources", [])), elapsed,
    )
    write_search_io_event(
        {
            "layer": "mcp_adapter",
            "phase": "web_search.result",
            "tool_id": "web_search",
            "query": query,
            "result": result,
            "elapsed_seconds": elapsed,
        }
    )
    return result


# Run the low-level raw SERP retrieval (unprocessed per-engine output).
async def _call_serp_search(args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "")
    logger.info("mcp.serp_search.start query_preview=%r", query[:160])
    started = time.perf_counter()
    result = await run_serp_search(
        query,
        region=str(args.get("region") or "us-en"),
        safesearch=str(args.get("safesearch") or "moderate"),
        timelimit=str(args["timelimit"]) if args.get("timelimit") else None,
        timeout_seconds=float(args.get("timeout_seconds") or 8.0),
        source_limit=3,
    )
    logger.info("mcp.serp_search.done elapsed=%.3fs", time.perf_counter() - started)
    return result


# Cancel outstanding background work (prefetch) at server shutdown.
async def shutdown() -> None:
    from core.search.prefetch import shutdown_prefetch

    await shutdown_prefetch()


# Dispatch an ASLM tool call to the matching search implementation.
async def call_tool(
    tool_id: str,
    arguments: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args = dict(arguments or {})
    if tool_id == "web_search":
        return await _call_web_search(args)
    if tool_id == "serp_search":
        return await _call_serp_search(args)
    raise ValueError(f"Unknown tool: {tool_id}")
