# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import contextlib
import re
import sys
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from adapters.mcp.logging_setup import setup_logging
from core.config import load_search_config
from services import run_read_page, run_web_search, run_deep_research
from services.web_search import shutdown_web_search

try:
    from mcp.server.fastmcp.server import Context as FastMCPContext
except Exception:  # pragma: no cover - optional during non-MCP imports
    FastMCPContext = Any  # type: ignore[assignment]


def _find_aslm_root() -> Path:
    current = Path(__file__).resolve().parent
    for p in [current, *current.parents]:
        if (p / "SYSTEM_PROMPT.md").exists() or (p / ".git").exists():
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


def _split_search_result_blocks(text: str) -> list[str]:
    normalized = (text or "").replace("\r\n", "\n").strip()
    if not normalized:
        return []
    return [part.strip() for part in _RESULT_BLOCK_SPLIT_RE.split(normalized) if part.strip()]


@mcp.tool()
async def web_search(
    query: str | list[str],
    context: FastMCPContext | dict[str, Any] | None = None,
) -> list[str]:
    """
    Search the web and return the strongest sources for a topic.

    Use it when you need:
    - recent news, developments, or announcements
    - articles, documentation, research pages, or official sources
    - one query or a small batch of alternative phrasings to compare

    What it returns:
    - around 10 results per query
    - title, URL, source snippet, and a larger preview when available
    - separate result blocks instead of one giant wall of text

    The date window is selected automatically based on the query type:
    news and finance queries are limited to the last month; shopping,
    troubleshooting, forum, and technical queries to the last year;
    academic, medical, and open-ended queries have no date restriction.

    Prompting hints for the model:
    - Prefer English as the default search language whenever the task allows it, even if the final answer is in another language.
    - Use other languages only when the situation truly requires them: the user explicitly asks for local-language sources, the topic is region-specific, or the key terminology is native to that language.
    - Prefer short, focused English queries over one oversized mixed-language query.
    - When the topic has several angles, use a small batch of short query variants, and keep them in English unless non-English search is clearly necessary.
    """
    logger.info(
        "mcp.web_search.start batch=%s query_preview=%r",
        isinstance(query, list),
        query[:2] if isinstance(query, list) else str(query)[:160],
    )
    if isinstance(query, list):
        queries = [q.strip() for q in query if isinstance(q, str) and q.strip()]
        if not queries:
            return ["Error: No queries provided."]
        try:
            tasks = [
                run_web_search(
                    q,
                    max_results=_WEB_SEARCH_RESULT_LIMIT,
                    use_yacy=True,
                    fetch_previews=True,
                )
                for q in queries[:_BATCH_QUERY_LIMIT]
            ]
            results = await _keepalive(context, "searching...", asyncio.gather(*tasks))
            blocks: list[str] = []
            for result in results:
                blocks.extend(_split_search_result_blocks(result))
            logger.info("mcp.web_search.done batch=True queries=%d blocks=%d", len(queries), len(blocks))
            return blocks
        except Exception:
            logger.exception("mcp.web_search.failed batch=True queries=%d", len(queries))
            raise

    try:
        result = await _keepalive(
            context,
            "searching...",
            run_web_search(
                query.strip(),
                max_results=_WEB_SEARCH_RESULT_LIMIT,
                use_yacy=True,
                fetch_previews=True,
            ),
        )
        blocks = _split_search_result_blocks(result)
        logger.info("mcp.web_search.done batch=False blocks=%d", len(blocks))
        return blocks
    except Exception:
        logger.exception("mcp.web_search.failed batch=False query_preview=%r", str(query)[:160])
        raise


@mcp.tool()
async def read_page(
    url: str | list[str],
    context: FastMCPContext | dict[str, Any] | None = None,
) -> list[str]:
    """
    Open a page and extract readable text from it.

    Use it when you need:
    - the full content of an article, documentation page, post, or thread
    - cleaner text after you already found promising URLs with search
    - a small batch read of several shortlisted pages

    It works best as the second step after search, when discovery is done
    and you want to actually read the sources.
    """
    logger.info(
        "mcp.read_page.start batch=%s url_preview=%r",
        isinstance(url, list),
        url[:2] if isinstance(url, list) else str(url)[:160],
    )
    if isinstance(url, list):
        urls = [u.strip() for u in url if isinstance(u, str) and u.strip()]
        if not urls:
            return ["Error: No URLs provided."]
        tasks = [run_read_page(u) for u in urls[:_BATCH_QUERY_LIMIT]]
        results = await _keepalive(context, "reading...", asyncio.gather(*tasks))
        logger.info("mcp.read_page.done batch=True urls=%d", len(urls))
        return results

    result = await _keepalive(context, "reading...", run_read_page(url.strip()))
    logger.info("mcp.read_page.done batch=False")
    return [result]


# ---------------------------------------------------------------------------
# Allowed depth values (validated before calling the pipeline)
# ---------------------------------------------------------------------------
_DEEP_RESEARCH_DEPTHS = {"low", "medium", "high", "extra"}
_DEEP_RESEARCH_HARD_TIMEOUTS = {
    "low":    300.0,
    "medium": 600.0,
    "high":   1800.0,
    "extra": 2400.0,
}


@mcp.tool()
async def deep_research(
    question: str,
    depth: str = "medium",
    context: FastMCPContext | dict[str, Any] | None = None,
) -> str:
    """
    Conduct autonomous deep research on a question.

    Use it when web_search is not enough and you need:
    - full-page extraction rather than only search snippets
    - iterative query refinement — gaps found during research trigger follow-up searches
    - source triage and de-duplication before synthesis
    - a structured markdown report rather than a list of snippets

    The tool runs a legacy-style deep-research flow:
      1. Plan — generates diverse sub-queries for the question
      2. Harvest — searches the web for each sub-query
      3. Triage — annotates each source with type, evidence strength, sub-topic
      4. Dedup/Filter — removes near-duplicates and low-information pages
      5. Synthesize — produces a structured markdown report with citations

    depth controls scope and runtime:
      "low"    — 4 queries, 15 sources max, ~5 min
      "medium" — 7 queries, 40 sources max, ~10 min  (default)
      "high"   — 10 queries, 80 sources max, ~15 min
      "extra"  — 14 queries, 120 sources max, ~20 min

    Returns a markdown-formatted research report. If any phase times out
    the tool returns a partial report rather than an error, so callers
    always get something useful.
    """
    depth = (depth or "medium").strip().lower()
    if depth not in _DEEP_RESEARCH_DEPTHS:
        depth = "medium"

    hard_timeout = _DEEP_RESEARCH_HARD_TIMEOUTS[depth]

    logger.info(
        "mcp.deep_research.start question_preview=%r depth=%s timeout=%.0fs",
        str(question)[:160], depth, hard_timeout,
    )

    try:
        report = await _keepalive(
            context,
            f"deep research [{depth}]...",
            run_deep_research(question=question.strip(), depth=depth),
        )
        logger.info(
            "mcp.deep_research.done depth=%s report_chars=%d",
            depth, len(report or ""),
        )
        return report or "Research complete but no report was generated."
    except Exception:
        logger.exception(
            "mcp.deep_research.failed depth=%s question_preview=%r",
            depth, str(question)[:160],
        )
        return (
            f"# Research: {question}\n\n"
            "Deep research failed due to an unexpected error. "
            "Try a lower depth or rephrase the question."
        )


if __name__ == "__main__":
    import os as _os

    yacy_started = False
    try:
        try:
            from Services import yacy_service

            yacy_started = yacy_service.start_yacy(log=True)
        except Exception:
            yacy_started = False

        mcp.run()
    finally:
        try:
            asyncio.get_event_loop().run_until_complete(shutdown_web_search())
        except Exception:
            pass
        if yacy_started:
            try:
                from Services import yacy_service

                yacy_service.stop_yacy(log=True)
            except Exception:
                pass

    # PyTorch (GLiNER / SentenceTransformer) spawns non-daemon inter-op threads
    # that keep the process alive after Ctrl+C even when the main thread has
    # finished.  All meaningful cleanup ran in the finally block above, so a
    # hard exit here is safe and prevents the ~1.5 GB zombie.
    _os._exit(0)
