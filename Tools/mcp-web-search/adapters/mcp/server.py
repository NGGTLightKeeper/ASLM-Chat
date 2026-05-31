# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import contextlib
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp.types import CallToolResult, TextContent
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from adapters.mcp.logging_setup import setup_logging
from adapters.mcp.tool_descriptions import (
    READ_PAGE_TOOL_DESCRIPTION,
    WEB_SEARCH_TOOL_DESCRIPTION,
)
from adapters.mcp.search_io_logger import write_search_io_event
from adapters.mcp.search_query_contract import (
    WebSearchQuery,
    coerce_search_effort,
    coerce_search_query,
)
from core.config import load_search_config
from services import run_read_page, run_web_search_rich
from services.web_search import shutdown_web_search

try:
    from mcp.server.fastmcp.server import Context as FastMCPContext
except Exception:  # pragma: no cover - optional during non-MCP imports
    FastMCPContext = Any  # type: ignore[assignment]


# Walk parent directories until ASLM project root markers are found.
def _find_aslm_root() -> Path:
    current = Path(__file__).resolve().parent
    for p in [current, *current.parents]:
        if (p / "Tools" / "SYSTEM_PROMPT.md").exists() or (p / ".git").exists():
            return p
    return current.parents[3] if len(current.parents) > 3 else current

ASLM_ROOT = _find_aslm_root()
if str(ASLM_ROOT) not in sys.path:
    sys.path.insert(0, str(ASLM_ROOT))

setup_logging()

mcp = FastMCP("mcp-web-search")
logger = __import__("logging").getLogger("adapters.mcp.server")
_CFG = load_search_config()
_WEB_SEARCH_RESULT_LIMIT = max(1, int(_CFG.search.max_results))
_BATCH_QUERY_LIMIT = max(1, int(_CFG.search.batch_query_limit))
_RESULT_BLOCK_SPLIT_RE = re.compile(r"\n\s*\n(?=\[\d+\])")
_KEEPALIVE_INTERVAL_SEC = 5.0
_KEEPALIVE_SEND_TIMEOUT_SEC = 1.5


class SearchSourceOutput(BaseModel):
    id: str
    rank: int
    title: str
    url: str
    domain: str
    display_domain: str
    favicon_url: str
    snippet: str
    preview: str = ""
    published_date: str = ""
    engine: str = ""
    trust_tier: str = "?"
    score: float = 0.0
    pdf_url: str = ""


class SearchSourceChipOutput(BaseModel):
    source_id: str
    domain: str
    display_domain: str
    favicon_url: str


class SearchCompactUiOutput(BaseModel):
    label: str
    source_chips: list[SearchSourceChipOutput]
    more_count: int = 0


class SearchUiOutput(BaseModel):
    status: str
    result_count: int
    compact: SearchCompactUiOutput | None = None


class SearchRichOutput(BaseModel):
    query: str
    search_id: str
    sources: list[SearchSourceOutput]
    model_context: str
    ui: SearchUiOutput


class ReadPageSourceOutput(BaseModel):
    rank: int
    url: str
    domain: str
    display_domain: str
    favicon_url: str
    ok: bool = True


class ReadPageUiOutput(BaseModel):
    kind: str = "read_page"
    status: str
    result_count: int
    sources: list[ReadPageSourceOutput]


# Send periodic MCP log pings while a long-running coroutine is in flight.
async def _keepalive(context: FastMCPContext | dict[str, Any] | None, message: str, coro):
    done = asyncio.Event()
    t0 = time.perf_counter()

    async def _ping_loop() -> None:
        session = None
        session_source = "context"
        if context is not None and not isinstance(context, dict):
            session = getattr(context, "session", None)
        if session is None:
            try:
                session = mcp._mcp_server.request_context.session
                session_source = "request_context"
            except Exception:
                logger.info("keepalive.no_session message=%r", message)
                return

        logger.info(
            "keepalive.start message=%r session_source=%s interval=%.1fs send_timeout=%.1fs",
            message, session_source, _KEEPALIVE_INTERVAL_SEC, _KEEPALIVE_SEND_TIMEOUT_SEC,
        )

        while not done.is_set():
            try:
                await asyncio.wait_for(
                    asyncio.shield(done.wait()),
                    timeout=_KEEPALIVE_INTERVAL_SEC,
                )
            except asyncio.TimeoutError:
                pass
            if not done.is_set():
                try:
                    send_t0 = time.perf_counter()
                    await asyncio.wait_for(
                        session.send_log_message(level="debug", data=message, logger="web-search"),
                        timeout=_KEEPALIVE_SEND_TIMEOUT_SEC,
                    )
                    logger.info(
                        "keepalive.ping_sent message=%r elapsed=%.3fs",
                        message, time.perf_counter() - send_t0,
                    )
                except Exception:
                    logger.warning("keepalive.ping_failed message=%r", message, exc_info=True)
                    return

    ping_task = asyncio.create_task(_ping_loop())
    try:
        result = await coro
        logger.info(
            "keepalive.done message=%r elapsed=%.3fs",
            message, time.perf_counter() - t0,
        )
        return result
    except Exception:
        logger.exception(
            "keepalive.failed message=%r elapsed=%.3fs",
            message, time.perf_counter() - t0,
        )
        raise
    finally:
        done.set()
        ping_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await ping_task


# Best-effort MCP progress notification when a live session context exists.
async def _report_progress(
    context: FastMCPContext | dict[str, Any] | None,
    progress: float,
    total: float,
    message: str,
) -> None:
    if context is None or isinstance(context, dict):
        return
    report = getattr(context, "report_progress", None)
    if report is None:
        return
    with contextlib.suppress(Exception):
        await report(progress, total, message)


# Split numbered search result blocks from a single model_context string.
def _split_search_result_blocks(text: str) -> list[str]:
    normalized = (text or "").replace("\r\n", "\n").strip()
    if not normalized:
        return []
    return [part.strip() for part in _RESULT_BLOCK_SPLIT_RE.split(normalized) if part.strip()]


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
    payload = {
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
    ReadPageUiOutput.model_validate(payload["ui"])
    return payload


# FastMCP tool handler for ranked web search with structured UI output.
async def web_search(
    query: WebSearchQuery,
    effort: str = "medium",
    context: FastMCPContext | dict[str, Any] | None = None,
) -> CallToolResult:
    started_at = time.perf_counter()
    query_text = coerce_search_query(query)
    search_effort = coerce_search_effort(query if effort == "medium" else effort)
    write_search_io_event(
        {
            "layer": "fastmcp_adapter",
            "phase": "web_search.coerced",
            "tool_id": "web_search",
            "raw_query": query,
            "coerced_query": query_text,
            "effort": search_effort,
        }
    )
    if not query_text:
        payload = {
            "query": "",
            "search_id": "srch_empty",
            "sources": [],
            "model_context": "Error: No query provided.",
            "ui": {
                "status": "error",
                "result_count": 0,
                "compact": {
                    "label": "Search failed",
                    "source_chips": [],
                    "more_count": 0,
                },
            },
        }
        SearchRichOutput.model_validate(payload)
        write_search_io_event(
            {
                "layer": "fastmcp_adapter",
                "phase": "web_search.result",
                "tool_id": "web_search",
                "coerced_query": query_text,
                "result": payload,
                "elapsed_seconds": time.perf_counter() - started_at,
            }
        )
        return CallToolResult(
            content=[TextContent(type="text", text=payload["model_context"])],
            structuredContent=payload,
            isError=True,
        )

    logger.info("mcp.web_search.start query_preview=%r", query_text[:160])
    await _report_progress(context, 0, 100, "search_started")
    try:
        payload = await _keepalive(
            context,
            "searching...",
            run_web_search_rich(
                query_text,
                max_results=_WEB_SEARCH_RESULT_LIMIT,
                effort=search_effort,
            ),
        )
        await _report_progress(context, 100, 100, "search_done")
        logger.info(
            "mcp.web_search.done sources=%d search_id=%s",
            len(payload.get("sources", [])) if isinstance(payload, dict) else 0,
            payload.get("search_id") if isinstance(payload, dict) else None,
        )
        SearchRichOutput.model_validate(payload)
        write_search_io_event(
            {
                "layer": "fastmcp_adapter",
                "phase": "web_search.result",
                "tool_id": "web_search",
                "coerced_query": query_text,
                "result": payload,
                "elapsed_seconds": time.perf_counter() - started_at,
            }
        )
        return CallToolResult(
            content=[TextContent(type="text", text=str(payload.get("model_context", "")))],
            structuredContent=payload,
        )
    except Exception:
        logger.exception("mcp.web_search.failed query_preview=%r", query_text[:160])
        raise


web_search.__doc__ = WEB_SEARCH_TOOL_DESCRIPTION
web_search = mcp.tool()(web_search)


# FastMCP tool handler for single or batched page reads.
async def read_page(
    url: str | list[str],
    focus: str = "",
    context: FastMCPContext | dict[str, Any] | None = None,
) -> CallToolResult:
    logger.info(
        "mcp.read_page.start batch=%s url_preview=%r",
        isinstance(url, list),
        url[:2] if isinstance(url, list) else str(url)[:160],
    )
    started_at = time.perf_counter()
    write_search_io_event(
        {
            "layer": "fastmcp_adapter",
            "phase": "read_page.request",
            "tool_id": "read_page",
            "url": url,
        }
    )
    if isinstance(url, list):
        urls = [u.strip() for u in url if isinstance(u, str) and u.strip()]
        if not urls:
            payload = _read_page_payload([], ["Error: No URLs provided."])
            write_search_io_event(
                {
                    "layer": "fastmcp_adapter",
                    "phase": "read_page.result",
                    "tool_id": "read_page",
                    "urls": [],
                    "result": payload,
                    "elapsed_seconds": time.perf_counter() - started_at,
                }
            )
            return CallToolResult(
                content=[TextContent(type="text", text=str(payload["model_context"]))],
                structuredContent=payload,
                isError=True,
            )
        tasks = [run_read_page(u, focus=focus) for u in urls[:_BATCH_QUERY_LIMIT]]
        results = await _keepalive(context, "reading...", asyncio.gather(*tasks))
        logger.info("mcp.read_page.done batch=True urls=%d", len(urls))
        payload = _read_page_payload(urls[:_BATCH_QUERY_LIMIT], results)
        write_search_io_event(
            {
                "layer": "fastmcp_adapter",
                "phase": "read_page.result",
                "tool_id": "read_page",
                "urls": urls[:_BATCH_QUERY_LIMIT],
                "result": payload,
                "elapsed_seconds": time.perf_counter() - started_at,
            }
        )
        return CallToolResult(
            content=[TextContent(type="text", text=str(payload["model_context"]))],
            structuredContent=payload,
            isError=payload["ui"]["status"] == "error",
        )

    url_text = url.strip()
    result = await _keepalive(context, "reading...", run_read_page(url_text, focus=focus))
    logger.info("mcp.read_page.done batch=False")
    payload = _read_page_payload([url_text], [result])
    write_search_io_event(
        {
            "layer": "fastmcp_adapter",
            "phase": "read_page.result",
            "tool_id": "read_page",
            "urls": [url_text],
            "result": payload,
            "elapsed_seconds": time.perf_counter() - started_at,
        }
    )
    return CallToolResult(
        content=[TextContent(type="text", text=str(payload["model_context"]))],
        structuredContent=payload,
        isError=payload["ui"]["status"] == "error",
    )


read_page.__doc__ = READ_PAGE_TOOL_DESCRIPTION
read_page = mcp.tool()(read_page)


if __name__ == "__main__":
    import os as _os

    try:
        # Evict stale/expired cache entries at startup to reclaim disk space.
        try:
            from services.web_search import _cache as _ws_cache
            from core.cache.hosted_cache import get_hosted_cache
            _ws_cache.evict_stale()
            get_hosted_cache().evict_expired()
        except Exception as _e:
            logger.debug("cache eviction at startup failed: %s", _e)

        mcp.run()
    finally:
        try:
            asyncio.get_event_loop().run_until_complete(shutdown_web_search())
        except Exception:
            pass
    # PyTorch (GLiNER / SentenceTransformer) spawns non-daemon inter-op threads
    # that keep the process alive after Ctrl+C even when the main thread has
    # finished.  All meaningful cleanup ran in the finally block above, so a
    # hard exit here is safe and prevents the ~1.5 GB zombie.
    _os._exit(0)
