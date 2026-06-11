# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

SERVER_ROOT = Path(__file__).resolve().parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from core.search.serp_api import run_serp_search

MCP_SERVER = {
    "id": "web_search",
    "name": "Web Search",
    "description": "Parallel raw SERP retrieval from general-purpose search engines.",
}

TOOLS = [
    {
        "id": "serp_search",
        "name": "SERP Search",
        "description": "Return up to three raw SERP sources from Google, Brave, and DuckDuckGo.",
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
                "timelimit": {
                    "type": "string",
                    "enum": ["d", "w", "m", "y"],
                },
                "timeout_seconds": {"type": "number", "default": 8.0},
            },
            "required": ["query"],
        },
    },
]


# Return whether this server supports the given engine or model.
def supports(engine: str | None = None, model_name: str | None = None) -> bool:
    return engine in (None, "ollama-service", "lms", "openai", "google-genai")


# Dispatch an ASLM tool call to the SERP search implementation.
async def call_tool(
    tool_id: str,
    arguments: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if tool_id != "serp_search":
        raise ValueError(f"Unknown tool: {tool_id}")
    args = dict(arguments or {})
    return await run_serp_search(
        str(args.get("query") or ""),
        region=str(args.get("region") or "us-en"),
        safesearch=str(args.get("safesearch") or "moderate"),
        timelimit=str(args["timelimit"]) if args.get("timelimit") else None,
        timeout_seconds=float(args.get("timeout_seconds") or 8.0),
        source_limit=3,
    )
