# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

SERVER_ROOT = Path(__file__).resolve().parents[2]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

ASLM_ROOT = Path(__file__).resolve().parents[4]
if str(ASLM_ROOT) not in sys.path:
    sys.path.insert(0, str(ASLM_ROOT))

from adapters.mcp.tool_descriptions import (
    MCP_SERVER_DESCRIPTION,
    READ_PAGE_TOOL_DESCRIPTION,
    WEB_SEARCH_TOOL_DESCRIPTION,
)
from core.config import load_search_config as _load_cfg
from core.fetch.thread_pool import io_pool as _io_pool  # noqa: F401 - initialise shared pool

_CFG = _load_cfg()
_MAX_RESULTS = max(1, int(_CFG.search.max_results))
_BATCH_LIMIT = max(1, int(_CFG.search.batch_query_limit))
logger = logging.getLogger("mcp_server_bridge")

MCP_SERVER = {
    "id": "web_search",
    "name": "Web Search",
    "description": MCP_SERVER_DESCRIPTION,
}

TOOLS = [
    {
        "id": "web_search",
        "name": "Web Search",
        "description": WEB_SEARCH_TOOL_DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "description": "A search string or a list of search strings.",
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                },
            },
            "required": ["query"],
        },
    },
    {
        "id": "read_page",
        "name": "Read Page",
        "description": READ_PAGE_TOOL_DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "description": "A URL string or a list of URLs.",
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                },
            },
            "required": ["url"],
        },
    },
]


def supports(engine: str | None = None, model_name: str | None = None) -> bool:
    return engine in ("ollama-service", "lms", "openai", "google-genai")


def _maybe_parse_list(val: Any) -> Any:
    if isinstance(val, str):
        stripped = val.strip()
        if stripped.startswith("["):
            import json

            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                logger.debug("Failed to parse list-like tool argument: %r", val[:200])
    return val


async def call_tool(
    tool_id: str,
    arguments: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> Any:
    args = dict(arguments or {})
    for key in ("query", "url"):
        if key in args:
            args[key] = _maybe_parse_list(args[key])

    if tool_id == "web_search":
        from services import run_web_search

        query = args.get("query", "")
        if isinstance(query, list):
            queries = [q.strip() for q in query if isinstance(q, str) and q.strip()]
            results = await asyncio.gather(
                *[run_web_search(q, max_results=_MAX_RESULTS) for q in queries[:_BATCH_LIMIT]],
                return_exceptions=True,
            )
            return "\n\n---\n\n".join(
                r if isinstance(r, str) else f"Error: {r}" for r in results
            )
        return await run_web_search(query.strip(), max_results=_MAX_RESULTS)

    if tool_id == "read_page":
        from services import run_read_page

        url = args.get("url", "")
        if isinstance(url, list):
            urls = [u.strip() for u in url if isinstance(u, str) and u.strip()]
            results = await asyncio.gather(
                *[run_read_page(u) for u in urls[:_BATCH_LIMIT]],
                return_exceptions=True,
            )
            return "\n\n---\n\n".join(
                r if isinstance(r, str) else f"Error: {r}" for r in results
            )
        return await run_read_page(url.strip())

    raise ValueError(f"Unknown tool: {tool_id}")
