# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import logging
import secrets
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
from adapters.mcp.search_io_logger import write_search_io_event
from adapters.mcp.search_query_contract import (
    SEARCH_QUERY_SCHEMA,
    coerce_search_effort,
    coerce_search_query,
    coerce_search_shopping,
)
from adapters.mcp.logging_setup import setup_logging
from core.config import load_search_config as _load_cfg
from core.fetch.thread_pool import io_pool as _io_pool  # noqa: F401 — initialise shared pool

setup_logging()

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
        "parameters": SEARCH_QUERY_SCHEMA,
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


# Report whether this bridge supports the given engine/model pair.
def supports(engine: str | None = None, model_name: str | None = None) -> bool:
    return engine in ("ollama-service", "lms", "openai", "google-genai")


# Parse JSON-encoded list strings passed as tool arguments.
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


# Normalize a URL host into a bare registrable domain label.
def _source_domain(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host.removeprefix("www.")


# Build a short human-readable label from a domain name.
def _display_domain(domain: str) -> str:
    parts = [part for part in (domain or "").split(".") if part]
    if len(parts) >= 2:
        label = parts[-2]
    elif parts:
        label = parts[0]
    else:
        return ""
    return label.replace("-", " ").title()


# DuckDuckGo favicon URL for a source domain chip.
def _favicon_url(domain: str) -> str:
    return f"https://icons.duckduckgo.com/ip3/{domain}.ico" if domain else ""


# Build one read_page source metadata record for UI chips.
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


# Assemble the structured read_page payload for one or many URLs.
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


# Dispatch MCP tool calls to web_search or read_page services.
async def call_tool(
    tool_id: str,
    arguments: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> Any:
    started_at = asyncio.get_running_loop().time()
    args = dict(arguments or {})
    for key in ("query", "url"):
        if key in args:
            args[key] = _maybe_parse_list(args[key])

    if tool_id == "web_search":
        from services import run_web_search_rich, validate_search_query

        query_text = coerce_search_query(args.get("query", ""))
        search_effort = coerce_search_effort(args)
        shopping = coerce_search_shopping(args)
        write_search_io_event(
            {
                "layer": "mcp_worker_bridge",
                "phase": "web_search.coerced",
                "tool_id": "web_search",
                "raw_arguments": args,
                "raw_query": args.get("query", ""),
                "coerced_query": query_text,
                "effort": search_effort,
                "shopping": shopping,
                "context": context or {},
            }
        )

        # ── Query quality gate ────────────────────────────────────────────────
        rejection = validate_search_query(query_text)
        if rejection:
            logger.warning(
                "bridge.web_search.rejected query_preview=%r reason=%r",
                query_text[:160], rejection[:120],
            )
            write_search_io_event(
                {
                    "layer": "mcp_worker_bridge",
                    "phase": "web_search.rejected",
                    "tool_id": "web_search",
                    "coerced_query": query_text,
                    "rejection": rejection,
                }
            )
            return {
                "query": query_text,
                "search_id": f"rejected_{secrets.token_hex(4)}",
                "sources": [],
                "model_context": rejection,
                "ui": {
                    "status": "rejected",
                    "result_count": 0,
                    "compact": {
                        "label": f"Query rejected: {query_text}",
                        "source_chips": [],
                        "more_count": 0,
                    },
                },
            }
        # ─────────────────────────────────────────────────────────────────────

        logger.info("bridge.web_search.start query_preview=%r", query_text[:160])
        result = await run_web_search_rich(
            query_text,
            max_results=_MAX_RESULTS,
            effort=search_effort,
            shopping=shopping,
        )
        write_search_io_event(
            {
                "layer": "mcp_worker_bridge",
                "phase": "web_search.result",
                "tool_id": "web_search",
                "coerced_query": query_text,
                "result": result,
                "elapsed_seconds": asyncio.get_running_loop().time() - started_at,
            }
        )
        source_count = len(result.get("sources", [])) if isinstance(result, dict) else 0
        logger.info(
            "bridge.web_search.done query_preview=%r sources=%d took=%.2fs",
            query_text[:160],
            source_count,
            asyncio.get_running_loop().time() - started_at,
        )
        return result

    if tool_id == "read_page":
        from services import run_read_page
        url = args.get("url", "")
        write_search_io_event(
            {
                "layer": "mcp_worker_bridge",
                "phase": "read_page.request",
                "tool_id": "read_page",
                "raw_arguments": args,
                "url": url,
                "context": context or {},
            }
        )
        if isinstance(url, list):
            urls = [u.strip() for u in url if isinstance(u, str) and u.strip()]
            logger.info("bridge.read_page.start batch=True urls=%d", len(urls[:_BATCH_LIMIT]))
            results = await asyncio.gather(
                *[run_read_page(u) for u in urls[:_BATCH_LIMIT]],
                return_exceptions=True,
            )
            texts = [r if isinstance(r, str) else f"Error: {r}" for r in results]
            payload = _read_page_payload(urls[:_BATCH_LIMIT], texts)
            write_search_io_event(
                {
                    "layer": "mcp_worker_bridge",
                    "phase": "read_page.result",
                    "tool_id": "read_page",
                    "urls": urls[:_BATCH_LIMIT],
                    "result": payload,
                    "elapsed_seconds": asyncio.get_running_loop().time() - started_at,
                }
            )
            logger.info(
                "bridge.read_page.done batch=True urls=%d status=%s took=%.2fs",
                len(urls[:_BATCH_LIMIT]),
                payload.get("ui", {}).get("status") if isinstance(payload.get("ui"), dict) else "",
                asyncio.get_running_loop().time() - started_at,
            )
            return payload
        url_text = url.strip()
        logger.info("bridge.read_page.start batch=False url=%r", url_text[:220])
        result = await run_read_page(url_text)
        payload = _read_page_payload([url_text], [result])
        write_search_io_event(
            {
                "layer": "mcp_worker_bridge",
                "phase": "read_page.result",
                "tool_id": "read_page",
                "urls": [url_text],
                "result": payload,
                "elapsed_seconds": asyncio.get_running_loop().time() - started_at,
            }
        )
        logger.info(
            "bridge.read_page.done batch=False status=%s took=%.2fs",
            payload.get("ui", {}).get("status") if isinstance(payload.get("ui"), dict) else "",
            asyncio.get_running_loop().time() - started_at,
        )
        return payload

    raise ValueError(f"Unknown tool: {tool_id}")
