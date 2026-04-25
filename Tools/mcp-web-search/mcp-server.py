# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SERVER_ROOT = Path(__file__).resolve().parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

ASLM_ROOT = Path(__file__).resolve().parents[2]
if str(ASLM_ROOT) not in sys.path:
    sys.path.insert(0, str(ASLM_ROOT))

from adapters.mcp.tool_descriptions import (
    MCP_SERVER_DESCRIPTION,
    READ_PAGE_TOOL_DESCRIPTION,
    WEB_SEARCH_TOOL_DESCRIPTION,
)
from core.config import load_search_config as _load_cfg
from core.fetch.thread_pool import io_pool as _io_pool  # noqa: F401 — initialise shared pool

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
                    "description": "A single web search query.",
                    "type": "string",
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


def _source_domain(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host.removeprefix("www.")


def _display_domain(domain: str) -> str:
    parts = [part for part in (domain or "").split(".") if part]
    if len(parts) >= 2:
        label = parts[-2]
    elif parts:
        label = parts[0]
    else:
        return ""
    return label.replace("-", " ").title()


def _favicon_url(domain: str) -> str:
    return f"https://icons.duckduckgo.com/ip3/{domain}.ico" if domain else ""


def _read_page_source(url: str, rank: int, result_text: str = "") -> dict[str, object]:
    domain = _source_domain(url)
    ok = not str(result_text or "").lstrip().lower().startswith("error:")
    return {
        "rank": rank,
        "url": (url or "").strip(),
        "domain": domain,
        "display_domain": _display_domain(domain) or domain,
        "favicon_url": _favicon_url(domain),
        "ok": ok,
    }


def _read_page_payload(urls: list[str], results: list[str]) -> dict[str, object]:
    sources = [
        _read_page_source(url, index, results[index - 1] if index - 1 < len(results) else "")
        for index, url in enumerate(urls, 1)
    ]
    ok_count = sum(1 for source in sources if bool(source.get("ok")))
    return {
        "query": ", ".join(urls),
        "sources": sources,
        "model_context": "\n\n".join(str(result or "") for result in results).strip(),
        "ui": {
            "kind": "read_page",
            "status": "done" if ok_count == len(sources) else ("partial" if ok_count else "error"),
            "result_count": len(sources),
            "sources": sources,
        },
    }


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
        from services import run_web_search_rich

        query = args.get("query", "")
        return await run_web_search_rich(str(query).strip(), max_results=_MAX_RESULTS)

    if tool_id == "read_page":
        from services import run_read_page
        url = args.get("url", "")
        if isinstance(url, list):
            urls = [u.strip() for u in url if isinstance(u, str) and u.strip()]
            results = await asyncio.gather(
                *[run_read_page(u) for u in urls[:_BATCH_LIMIT]],
                return_exceptions=True,
            )
            texts = [r if isinstance(r, str) else f"Error: {r}" for r in results]
            return _read_page_payload(urls[:_BATCH_LIMIT], texts)
        url_text = url.strip()
        result = await run_read_page(url_text)
        return _read_page_payload([url_text], [result])

    raise ValueError(f"Unknown tool: {tool_id}")
