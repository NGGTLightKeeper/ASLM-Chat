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

# Force UTF-8 on the process stdout/stderr. The ASLM tool worker re-execs this module
# in-process on every call, then prints the JSON result envelope with ensure_ascii=False.
# Search results routinely contain emoji/CJK from page content; if the worker's stdout
# codec is not UTF-8 (Windows default is cp125x), that print raises UnicodeEncodeError
# AFTER the tool already finished — the "finishes then crashes" failure. Reconfiguring
# here guarantees the envelope encodes regardless of the parent's environment.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 — older/odd streams without reconfigure: best-effort
        pass

from core.logging_setup import setup_logging
from core.mcp_contract import (
    MCP_SERVER_DESCRIPTION,
    READ_PAGE_TOOL_DESCRIPTION,
    SEARCH_QUERY_SCHEMA,
    WEB_SEARCH_TOOL_DESCRIPTION,
    coerce_search_academic,
    coerce_search_effort,
    coerce_search_query,
    coerce_search_shopping,
)
from core.read import run_read_page
from core.search.web_search import run_web_search
from core.search_io_logger import write_search_io_event
from urllib.parse import urlparse

# Wire rotating file logs (web_search.log / read_page.log / core.log / mcp_trace.log)
# and the model IO log before anything runs, exactly like the legacy adapter.
setup_logging()
logger = logging.getLogger("mcp.server")

_evicted = False


# Reclaim disk from expired cache entries once per process, on first tool call.
def _evict_caches_once() -> None:
    global _evicted
    if _evicted:
        return
    _evicted = True
    try:
        from core.cache import get_page_cache
        from core.cache.hosted_cache import get_hosted_cache

        get_hosted_cache().evict_expired()
        get_page_cache().evict_stale()
    except Exception as exc:  # noqa: BLE001 — housekeeping must never block a search
        logger.debug("cache eviction skipped: %s", exc)

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


# Return whether this server supports the given engine or model.
def supports(engine: str | None = None, model_name: str | None = None) -> bool:
    return engine in (None, "ollama-service", "lms", "openai", "google-genai")


# Run the ranked web_search pipeline (the model-facing default tool).
#
# The model controls only query/effort/shopping. Recency (timelimit) is parsed from the
# query, region is routed by language, and safe-search stays moderate — none are model-
# facing knobs. Arguments are coerced (a model may stringify or wrap them).
async def _call_web_search(args: dict[str, Any]) -> dict[str, Any]:
    query = coerce_search_query(args.get("query", ""))
    effort = coerce_search_effort(args)
    shopping = coerce_search_shopping(args)
    academic = coerce_search_academic(args)

    write_search_io_event(
        {
            "layer": "mcp_adapter",
            "phase": "web_search.request",
            "tool_id": "web_search",
            "query": query,
            "effort": effort,
            "shopping": shopping,
            "academic": academic,
        }
    )
    logger.info("mcp.web_search.start effort=%s shopping=%s academic=%s query_preview=%r",
                effort, shopping, academic, query[:160])
    started = time.perf_counter()
    try:
        result = await run_web_search(query, effort=effort, shopping=shopping, academic=academic)
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


# Parse a JSON-encoded list passed as a string tool argument (some callers stringify).
def _maybe_parse_list(val: Any) -> Any:
    if isinstance(val, str) and val.strip().startswith("["):
        import json
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return parsed
        except Exception:  # noqa: BLE001
            logger.debug("failed to parse list-like tool argument: %r", val[:200])
    return val


# Bare registrable host for a URL (no scheme/userinfo/port/www.).
def _source_domain(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host.removeprefix("www.")


# Short human label from a domain (example.com -> "Example").
def _display_domain(domain: str) -> str:
    parts = [p for p in (domain or "").split(".") if p]
    if len(parts) >= 2:
        label = parts[-2]
    elif parts:
        label = parts[0]
    else:
        return ""
    return label.replace("-", " ").title()


# DuckDuckGo favicon URL for a source chip.
def _favicon_url(domain: str) -> str:
    return f"https://icons.duckduckgo.com/ip3/{domain}.ico" if domain else ""


# One read_page source record (UI chip metadata + ok flag from the result text).
def _read_page_source(url: str, rank: int, result_text: str = "") -> dict[str, Any]:
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


# Assemble the structured read_page payload for one or many URLs (legacy bridge shape).
def _read_page_payload(urls: list[str], results: list[str]) -> dict[str, Any]:
    sources = [
        _read_page_source(url, i, results[i - 1] if i - 1 < len(results) else "")
        for i, url in enumerate(urls, 1)
    ]
    ok_count = sum(1 for s in sources if s.get("ok"))
    status = "done" if ok_count == len(sources) else ("partial" if ok_count else "error")
    return {
        "query": ", ".join(urls),
        "sources": sources,
        "model_context": "\n\n".join(str(r or "") for r in results).strip(),
        "ui": {
            "kind": "read_page",
            "status": status,
            "result_count": len(sources),
            "sources": sources,
        },
    }


# Fetch one or many URLs as markdown and wrap them in the structured payload.
async def _call_read_page(args: dict[str, Any]) -> dict[str, Any]:
    import asyncio

    from core.config import load_search_config

    batch_limit = max(1, int(load_search_config().search.batch_query_limit))
    url = _maybe_parse_list(args.get("url", ""))
    write_search_io_event(
        {"layer": "mcp_adapter", "phase": "read_page.request", "tool_id": "read_page", "url": url}
    )

    if isinstance(url, list):
        urls = [u.strip() for u in url if isinstance(u, str) and u.strip()][:batch_limit]
        logger.info("mcp.read_page.start batch=True urls=%d", len(urls))
        results = await asyncio.gather(*[run_read_page(u) for u in urls], return_exceptions=True)
        texts = [r if isinstance(r, str) else f"Error: {r}" for r in results]
        payload = _read_page_payload(urls, texts)
    else:
        url_text = str(url).strip()
        logger.info("mcp.read_page.start batch=False url=%r", url_text[:220])
        text = await run_read_page(url_text)
        payload = _read_page_payload([url_text], [text])

    write_search_io_event(
        {"layer": "mcp_adapter", "phase": "read_page.result", "tool_id": "read_page",
         "result": payload}
    )
    logger.info("mcp.read_page.done status=%s count=%d",
                payload["ui"]["status"], payload["ui"]["result_count"])
    return payload


# Cancel outstanding background work (prefetch) and release this process's HTTP resources
# at server shutdown. The warm browser daemon is intentionally left running so it stays warm
# for the next tool call; it self-terminates on its own idle timeout (daemon_idle_shutdown_sec).
async def shutdown() -> None:
    from core.fetch.browser.client import shutdown_browser
    from core.search import serp_api
    from core.search.prefetch import shutdown_prefetch

    await shutdown_prefetch()
    await shutdown_browser()
    if serp_api._shared_transport is not None:
        await serp_api._shared_transport.close()


# Dispatch an ASLM tool call to the matching search implementation.
async def call_tool(
    tool_id: str,
    arguments: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args = dict(arguments or {})
    _evict_caches_once()
    if tool_id == "web_search":
        return await _call_web_search(args)
    if tool_id == "read_page":
        return await _call_read_page(args)
    raise ValueError(f"Unknown tool: {tool_id}")
