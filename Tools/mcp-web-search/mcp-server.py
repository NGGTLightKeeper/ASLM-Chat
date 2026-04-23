# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

SERVER_ROOT = Path(__file__).resolve().parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

ASLM_ROOT = Path(__file__).resolve().parents[2]
if str(ASLM_ROOT) not in sys.path:
    sys.path.insert(0, str(ASLM_ROOT))

from core.config import load_search_config as _load_cfg
from core.fetch.thread_pool import io_pool as _io_pool  # noqa: F401 — initialise shared pool

_CFG = _load_cfg()
_MAX_RESULTS = max(1, int(_CFG.search.max_results))
_BATCH_LIMIT = max(1, int(_CFG.search.batch_query_limit))
_SANDBOX_ROOT = ASLM_ROOT / "_sandbox"
logger = logging.getLogger("mcp_server_bridge")

MCP_SERVER = {
    "id": "web_search",
    "name": "Web Search",
    "description": "Search, page reading, deep research, and file import tools.",
}

TOOLS = [
    {
        "id": "web_search",
        "name": "Web Search",
        "description": (
            "Search the web and return the strongest sources for a topic. "
            "Single query or a list of query variants (up to 10). "
            "Returns title, URL, snippet, and page preview per result."
        ),
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
        "description": (
            "Fetch and extract text content from one or more URLs. "
            "Handles HTML, PDF, YouTube (transcript), GitHub. "
            "Use after web_search to read full content of shortlisted pages."
        ),
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
    {
        "id": "deep_research",
        "name": "Deep Research",
        "description": (
            "Run an autonomous agentic research loop and return a Markdown report. "
            "Iteratively searches, reads pages, and synthesizes sources. "
            "WARNING: runs for a long time, wait for completion."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Research question or task.",
                },
                "depth": {
                    "type": "string",
                    "default": "standard",
                    "enum": ["standard", "overdrive"],
                },
            },
            "required": ["question"],
        },
    },
    {
        "id": "import_web_file",
        "name": "Import Web File",
        "description": (
            "Download a file from a URL and save it to the sandbox workspace. "
            "Only call when the URL points to a real downloadable file. "
            "Supported: documents, media, archives, source code. Blocked: executables."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "save_to": {
                    "type": "string",
                    "description": "Subdirectory inside _sandbox/ to save the file.",
                    "default": "downloads/",
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

    if tool_id == "deep_research":
        from services.deep_research.orchestrator import run_deep_research
        return await run_deep_research(
            question=args.get("question", ""),
            depth=args.get("depth", "standard"),
        )

    if tool_id == "import_web_file":
        from core.fetch.file_importer import download_file
        return await download_file(
            url=args.get("url", ""),
            sandbox_root=_SANDBOX_ROOT,
            save_to=args.get("save_to", "downloads/"),
        )

    raise ValueError(f"Unknown tool: {tool_id}")
