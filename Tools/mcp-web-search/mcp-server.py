# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import sys
import time
from pathlib import Path
from typing import Any

SERVER_ROOT = Path(__file__).resolve().parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

ASLM_ROOT = Path(__file__).resolve().parents[2]
if str(ASLM_ROOT) not in sys.path:
    sys.path.insert(0, str(ASLM_ROOT))

SRC_ROOT = Path(__file__).resolve().parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

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
            "Search the internet via DDGS and optionally YaCy. "
            "Single query returns previews; multiple queries return compact batch results."
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
                "limit": {
                    "type": "integer",
                    "description": "Maximum result count per query.",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "id": "read_page",
        "name": "Read Page",
        "description": "Read one or more URLs and extract page text or save structured page dumps.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "description": "A URL string or a list of URLs to read.",
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                },
                "save": {
                    "type": "boolean",
                    "description": "Save extracted content to task/pages/ instead of returning it.",
                    "default": False,
                },
            },
            "required": ["url"],
        },
    },
    {
        "id": "deep_research",
        "name": "Deep Research",
        "description": "Run the long-form research pipeline and return the final report.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Research question or task.",
                },
                "depth": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "extra"],
                    "default": "medium",
                },
            },
            "required": ["query"],
        },
    },
    {
        "id": "import_web_file",
        "name": "Import Web File",
        "description": "Download a confirmed file URL into the task workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "save_to": {
                    "type": "string",
                    "description": "Subdirectory inside task/ to save the file.",
                    "default": "downloads/",
                },
                "allowed_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional category filter such as text, media, archive, or data.",
                },
                "max_size_mb": {
                    "type": "integer",
                    "description": "Maximum download size in MB.",
                    "default": 50,
                },
            },
            "required": ["url"],
        },
    },
]


def supports(engine: str | None = None, model_name: str | None = None) -> bool:
    """Expose this tool server only for Ollama tool-calling flows."""

    return engine == "ollama-service"


_REGISTERED_TOOL_FUNCTIONS: dict[str, Any] | None = None


class _ToolCollector:
    """Capture FastMCP-style tool registrations into a simple function map."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}
        self._mcp_server = None

    def tool(self, name: str | None = None):
        def decorator(fn):
            self.tools[name or fn.__name__] = fn
            return fn

        return decorator


def _get_registered_tool_functions() -> dict[str, Any]:
    """Lazily build a mapping of tool ids to the nested FastMCP handlers."""

    global _REGISTERED_TOOL_FUNCTIONS

    if _REGISTERED_TOOL_FUNCTIONS is not None:
        return _REGISTERED_TOOL_FUNCTIONS

    collector = _ToolCollector()
    register_tools(collector)
    _REGISTERED_TOOL_FUNCTIONS = collector.tools
    return _REGISTERED_TOOL_FUNCTIONS


async def call_tool(tool_id: str, arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> Any:
    """Generic ASLM-compatible dispatcher for Web Search tools."""

    tool_functions = _get_registered_tool_functions()
    handler = tool_functions.get(tool_id)
    if handler is None:
        raise ValueError(f"Unknown tool: {tool_id}")

    return await handler(**(arguments or {}))


def _is_yacy_enabled() -> bool:
    """Return whether YaCy is enabled in ASLM settings or legacy mode."""

    try:
        from Settings import settings as app_settings

        return bool(app_settings.get("use-yacy", False))
    except Exception:
        return True


def _ensure_yacy_started() -> bool:
    """Start YaCy on demand when it is enabled and manageable from ASLM."""

    if not _is_yacy_enabled():
        return False

    try:
        from Services import yacy_service

        return bool(yacy_service.start_yacy(log=False))
    except Exception:
        return True


def _format_found_line(total: int, yacy_count: int, ddgs_count: int, yacy_enabled: bool) -> str:
    """Build a user-facing result summary line."""

    if yacy_enabled:
        return f"Found   : {total}  (YaCy: {yacy_count}  DDGS: {ddgs_count})"
    return f"Found   : {total}  (DDGS: {ddgs_count})"

# Tool registration entry point.
def register_tools(mcp) -> None:
    """Register all Web Search MCP tools on the given FastMCP instance."""
    from engine import (
        SearchResult,
        async_yacy_search,
        async_ddgs_search,
        async_add_to_yacy_index,
        _debug_log,
        _short_url,
        _is_youtube,
        _is_skippable,
        _is_downloadable_ext,
        _badge_type,
        _badge_engine,
        _is_antibot,
        _fetch_previews,
        _proportional_merge,
        _proportional_allot,
        _parse_url_arg,
        _fetch_reddit_json,
        _fetch_with_camoufox,
        _fetch_with_curl_cffi,
        _fetch_json_api,
        _url_to_slug,
        _youtube_transcript,
        _domain_registry,
        _extra_research,
        _YACY_SEARCH_TIMEOUT,
        _DDGS_SEARCH_TIMEOUT,
        _HERE,
        PROJECT_DIR,
        SCRIPTS_DIR,
        OUT_DIR,
    )
    from file_importer import download_file
    from urllib.parse import urlparse

    # Search tools.
    # Register the combined web search tool.
    @mcp.tool()
    async def web_search(query: str | list[str], limit: int = 10) -> list[str]:
        """
        Internet search. Always uses both sources in parallel:
        half results from local YaCy index (+ global P2P network),
        half from DDGS (DuckDuckGo/Google/Brave/Bing).

        Single query: returns results with page previews.
        Multiple queries (list): runs all in parallel, returns structured JSON - no previews, snippets only.
          - Up to 10 queries; total results capped at limit*len(queries), distributed proportionally.

        Preview mode is configured in tools/mcp-web-search/config.py:
          WEB_SEARCH_MODE = "legacy" | "semantic"
        """
        import json as _json
        yacy_enabled = _ensure_yacy_started()

        # --- batch mode ---
        if isinstance(query, list):
            queries = [q.strip() for q in query if isinstance(q, str) and q.strip()][:10]
            if not queries:
                return ['{"error": "No queries provided"}']

            total_limit = limit * len(queries)
            total_limit = max(5, min(total_limit, 50))

            t0 = time.time()
            per_fetch = max(12, total_limit // max(len(queries), 1) + 6)

            # Search one query across both backends.
            async def _search_one_batch(q: str) -> list[SearchResult]:
                ddgs_task  = asyncio.wait_for(async_ddgs_search(q, per_fetch), timeout=_DDGS_SEARCH_TIMEOUT)
                if yacy_enabled:
                    yacy_task = asyncio.wait_for(async_yacy_search(q, per_fetch), timeout=_YACY_SEARCH_TIMEOUT)
                    yr, dr = await asyncio.gather(yacy_task, ddgs_task, return_exceptions=True)
                    yr = yr if isinstance(yr, list) else []
                else:
                    yr = []
                    dr = await ddgs_task
                dr = dr if isinstance(dr, list) else []
                return _proportional_merge(yr, dr, per_fetch) if yacy_enabled else dr[:per_fetch]

            raw = await asyncio.gather(*[_search_one_batch(q) for q in queries], return_exceptions=True)
            per_query: list[list[SearchResult]] = [r if isinstance(r, list) else [] for r in raw]

            found_counts = [len(r) for r in per_query]
            allotments = _proportional_allot(found_counts, total_limit)

            ms = int((time.time() - t0) * 1000)
            total_returned = 0
            out_queries = []

            for q, results, allot in zip(queries, per_query, allotments):
                trimmed = results[:allot]
                total_returned += len(trimmed)
                out_queries.append({
                    "query": q,
                    "count": len(trimmed),
                    "found": len(results),
                    "results": [
                        {
                            "title": r.title or "",
                            "url": r.url,
                            "snippet": (r.snippet or "")[:350],
                            "engine": r.engine or "",
                        }
                        for r in trimmed
                    ],
                })

            out_blocks: list[str] = []
            for qdata in out_queries:
                q_hdr = "\n".join([
                    f"Web Search - {ms}ms",
                    f"Query   : {qdata['query']}",
                    _format_found_line(
                        qdata["count"],
                        sum(1 for r in qdata["results"] if "yacy" in r["engine"].lower()),
                        sum(1 for r in qdata["results"] if "yacy" not in r["engine"].lower()),
                        yacy_enabled,
                    ),
                ])
                out_blocks.append(q_hdr)
                for i, r in enumerate(qdata["results"], 1):
                    lines = [
                        f"[{i}] {_badge_type(r['url'])} {_badge_engine(r['engine'])}",
                        f"Title   : {r['title'] or '-'}",
                        f"URL     : {r['url']}",
                        f"Snippet : {r['snippet'] or '-'}",
                    ]
                    out_blocks.append("\n".join(lines))
            return out_blocks

        # --- single query mode ---
        t0 = time.time()

        ddgs_task  = asyncio.wait_for(async_ddgs_search(query, limit), timeout=_DDGS_SEARCH_TIMEOUT)
        if yacy_enabled:
            yacy_task = asyncio.wait_for(async_yacy_search(query, limit), timeout=_YACY_SEARCH_TIMEOUT)
            yacy_res, ddgs_res = await asyncio.gather(yacy_task, ddgs_task, return_exceptions=True)
            yacy_res = yacy_res if isinstance(yacy_res, list) else []
        else:
            yacy_res = []
            ddgs_res = await ddgs_task
        ddgs_res = ddgs_res if isinstance(ddgs_res, list) else []

        yn_raw, dn_raw = len(yacy_res), len(ddgs_res)

        total_found = yn_raw + dn_raw
        if total_found == 0:
            yacy_take = ddgs_take = 0
        elif yn_raw == 0:
            yacy_take, ddgs_take = 0, limit
        elif dn_raw == 0:
            yacy_take, ddgs_take = limit, 0
        else:
            yacy_take = max(1, round(limit * yn_raw / total_found))
            ddgs_take = limit - yacy_take
            if yacy_take > yn_raw:
                yacy_take = yn_raw
                ddgs_take = min(limit - yacy_take, dn_raw)
            elif ddgs_take > dn_raw:
                ddgs_take = dn_raw
                yacy_take = min(limit - ddgs_take, yn_raw)

        yacy_res = yacy_res[:yacy_take]
        ddgs_res  = ddgs_res[:ddgs_take]
        yn, dn = len(yacy_res), len(ddgs_res)

        results = [x for pair in zip(yacy_res, ddgs_res) for x in pair]
        results += yacy_res[len(ddgs_res):] + ddgs_res[len(yacy_res):]

        # YaCy auto-learn: index trusted URLs from DDGS results
        if yacy_enabled and ddgs_res:
            try:
                trust_json = _HERE.parent / "deep-research" / "config" / "trust_registry.json"
                if trust_json.exists():
                    import json
                    with open(trust_json, "r", encoding="utf-8") as f:
                        td = json.load(f)

                    # Check whether a result belongs to a trusted domain.
                    def _is_trusted(url: str) -> bool:
                        nl = urlparse(url).netloc.lower()
                        for d in td.get("domains", []):
                            p = d.get("pattern", "")
                            if nl == p or nl.endswith("." + p):
                                return True
                        return False

                    for item in ddgs_res:
                        if item.url and _is_trusted(item.url):
                            asyncio.create_task(async_add_to_yacy_index(item.url))
            except Exception as e:
                _debug_log(f"YaCy auto-learn error: {e}")

        ms = int((time.time()-t0)*1000)

        if not results:
            return [f"Web Search - no results - {ms}ms\nQuery: {query}"]

        previews = await _fetch_previews(results)
        previews += [""] * (len(results) - len(previews))

        # Format one result block for display.
        def _fmt_result(i: int, r: SearchResult, preview: str) -> str:
            lines = [
                f"[{i}] {_badge_type(r.url)} {_badge_engine(r.engine)}",
                f"Title   : {r.title or '-'}",
                f"URL     : {_short_url(r.url)}",
                f"Snippet : {(r.snippet or '-')[:400]}",
            ]
            if preview:
                lines.append(f"Preview : {preview}")
            return "\n".join(lines)

        downloadable = [r for r in results if _is_downloadable_ext(r.url)]

        hdr = "\n".join([
            f"Web Search - {ms}ms",
            f"Query   : {query}",
            _format_found_line(len(results), yn, dn, yacy_enabled),
        ])
        blocks = [hdr] + [_fmt_result(i, r, previews[i-1]) for i, r in enumerate(results, 1)]
        if downloadable:
            hint = "Downloadable files found - use import_web_file(url) to save to task workspace."
            blocks.append(hint)
        return blocks

    # Register the page-reading tool.
    @mcp.tool()
    async def read_page(url: str | list[str], save: bool = False) -> list[str]:
        """
        Reads a web page and returns its text content (HTML, PDF, GitHub, YouTube).
        Accepts a single URL string or a list of URLs for batch reading.
        Automatically routes requests based on domain registry:
          - json_api domains -> uses API endpoint instead of web page
          - hardened domains -> uses curl_cffi with Chrome TLS fingerprint
          - fortress/skip domains -> skipped
        Falls back to httpx for unknown domains.

        save=True: save each page as JSON to task/pages/<slug>.json in the sandbox workspace.
          Returns only "Saved: <path>" on success or an error message - no page content.
          Nothing is written if the page fails to load.
        """
        import json as _json

        urls = _parse_url_arg(url)
        if not urls:
            return ["Error: argument must be a string or array of strings."]

        if save:
            workspace_root = Path(PROJECT_DIR).parent.parent
            pages_dir = workspace_root / "task" / "pages"
            pages_dir.mkdir(parents=True, exist_ok=True)

        # Read one URL and normalize the extracted text.
        async def _process_single(u: str) -> str:
            if _is_youtube(u):
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(None, _youtube_transcript, u)
            if _is_skippable(u):
                if _is_downloadable_ext(u):
                    return (
                        f"Source: {u}\n"
                        f"This URL points to a downloadable file, not a web page.\n"
                        f"Use import_web_file(\"{u}\") to save it to the task workspace."
                    )
                return f"Source: {u}\nSkipped: domain is blocked or unsupported."

            _host = urlparse(u).netloc.lower().removeprefix("www.")
            if _host in ("reddit.com", "old.reddit.com") or _host.endswith(".reddit.com"):
                try:
                    text = await _fetch_reddit_json(u)
                    if text.strip():
                        return f"Source: {u}\n\n{text}"
                except Exception as e:
                    _debug_log(f"reddit_json failed for {u}: {e}")
                return f"Source: {u}\nError: Reddit fetch failed."

            reg = _domain_registry
            method = "http"
            tier = "unknown"
            json_api_hint = None
            if reg is not None:
                info = reg.lookup(u)
                method = info.method
                tier = info.tier
                json_api_hint = info.json_api_hint

            if method == "json_api":
                api_url = json_api_hint or u
                if "<query>" in api_url or "<q>" in api_url:
                    from urllib.parse import urlparse as _up, unquote as _uq
                    path = _uq(_up(u).path).strip("/").split("/")[-1]
                    api_url = api_url.replace("<query>", path).replace("<q>", path)
                try:
                    text = await _fetch_json_api(api_url)
                    return f"Source: {u}\nAPI: {api_url}\n\n{text}"
                except Exception as e:
                    return f"Source: {u}\nError: JSON API fetch failed: {e}"

            try:
                from ingest.router import ingest_router
                b = await ingest_router.ingest(u)
                return f"Source: {u}\n\n{b.markdown_content}"
            except ImportError:
                pass
            except Exception as e:
                _debug_log(f"read_page ingest_router error for {u}: {e}")

            if method == "camoufox" or tier == "fortress":
                try:
                    text = await _fetch_with_camoufox(u)
                    if text.strip():
                        return f"Source: {u}\n\n{text}"
                except Exception as e:
                    _debug_log(f"camoufox failed for {u}: {e}")
                    return f"Source: {u}\nError: Failed to load (camoufox): {e}"

            if tier == "hardened":
                try:
                    text = await _fetch_with_curl_cffi(u)
                    return f"Source: {u}\n\n{text[:12000]}"
                except Exception as e:
                    return f"Source: {u}\nError: curl_cffi fetch failed: {e}"

            try:
                import httpx, re
                async with httpx.AsyncClient(follow_redirects=True, timeout=15) as c:
                    r = await c.get(u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                    r.raise_for_status()
                    raw = r.text
                    raw = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', raw, flags=re.IGNORECASE | re.DOTALL)
                    text = re.sub(r"\s{2,}", "\n", re.sub(r"<[^>]+>", " ", raw)).strip()
                if _is_antibot(text):
                    try:
                        text = await _fetch_with_curl_cffi(u)
                    except Exception:
                        return f"Source: {u}\nError: Blocked by anti-bot."
                return f"Source: {u}\n\n{text[:12000]}"
            except Exception as e:
                try:
                    text = await _fetch_with_curl_cffi(u)
                    return f"Source: {u}\n\n{text[:12000]}"
                except Exception as e2:
                    return f"Source: {u}\nError: Failed to load: {e2}"

        if save:
            # Read and persist one URL as JSON.
            async def _save_single(u: str) -> str:
                content = await _process_single(u)
                if "Error:" in content:
                    return content
                slug = _url_to_slug(u)
                dest = pages_dir / f"{slug}.json"
                payload = _json.dumps(
                    {"url": u, "content": content.splitlines()},
                    ensure_ascii=False, indent=2
                )
                dest.write_text(payload, encoding="utf-8")
                return f"Saved: task/pages/{dest.name}"

            tasks = [_save_single(u) for u in urls]
        else:
            tasks = [_process_single(u) for u in urls]

        results = await asyncio.gather(*tasks)
        return list(results)

    # Research tools.
    # Register the deep research tool.
    @mcp.tool()
    async def deep_research(query: str, depth: str = "medium") -> str:
        """
        Runs deep research on a given question and returns a final report.
        WARNING: this tool runs for a long time (3 to 15 minutes). Wait for completion.
        depth: 'low' | 'medium' | 'high' | 'extra'
        """
        import glob
        import sys
        import os
        import datetime

        _ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        task_id = f"research_{_ts}"
        script  = SCRIPTS_DIR / "deep_research.py"

        if not script.exists():
            return f"Error: Script not found: {script}"

        try:
            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            env.pop("PYTHONPATH", None)
            yacy_enabled = _ensure_yacy_started()
            cmd = [sys.executable, "-u", str(script), query, "--depth", depth, "--id", task_id]
            if not yacy_enabled:
                cmd.append("--no-yacy")

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(PROJECT_DIR), env=env,
            )

            stdout_chunks = []
            stderr_chunks = []

            # Drain the child stdout stream.
            async def _drain_stdout():
                while True:
                    chunk = await proc.stdout.read(4096)
                    if not chunk:
                        break
                    stdout_chunks.append(chunk)

            # Drain the child stderr stream.
            async def _drain_stderr():
                while True:
                    chunk = await proc.stderr.read(4096)
                    if not chunk:
                        break
                    stderr_chunks.append(chunk)

            drain_out = asyncio.create_task(_drain_stdout())
            drain_err = asyncio.create_task(_drain_stderr())

            _ping_tick = 0
            while proc.returncode is None:
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
                _ping_tick += 1
                if _ping_tick % 5 == 0:  # ping every ~10 s
                    try:
                        session = mcp._mcp_server.request_context.session
                        await session.send_log_message(level="debug", data="researching...", logger="deep-research")
                    except Exception:
                        pass

            await drain_out
            await drain_err

            stdout = b"".join(stdout_chunks)
            stderr = b"".join(stderr_chunks)

            report = None

            if stdout:
                for line in stdout.decode('utf-8', errors='replace').splitlines():
                    if line.startswith("REPORT_PATH:"):
                        p = Path(line.split(":", 1)[1].strip())
                        if p.exists():
                            report = p
                            break

            if not report:
                for candidate in [
                    OUT_DIR / task_id / "report.md",
                    PROJECT_DIR / "_out" / task_id / "report.md",
                    PROJECT_DIR / "deep-research" / "_out" / task_id / "report.md",
                    PROJECT_DIR / "output" / task_id / "report.md",
                ]:
                    if candidate.exists():
                        report = candidate
                        break

            if not report:
                for match in glob.glob(str(PROJECT_DIR / "**" / task_id / "report.md"), recursive=True):
                    report = Path(match)
                    break

            if report:
                return report.read_text(encoding="utf-8", errors="replace")

            err = stderr.decode('utf-8', errors='replace')[-3000:]
            out = stdout.decode('utf-8', errors='replace')[-1000:]
            return (
                f"Error: Process finished (code {proc.returncode}) but report.md not found.\n"
                f"OUT_DIR: {OUT_DIR}\nPROJECT_DIR: {PROJECT_DIR}\n"
                f"task_id: {task_id}\n\nStderr:\n{err}\nStdout:\n{out}"
            )

        except Exception as e:
            return f"Error: Launch error: {e}"

    # Download helpers.

    # Keep the MCP connection alive while awaiting a long download.
    async def _keepalive_download(coro, interval: float = 5.0):
        """Run a coroutine while sending periodic log pings to keep the MCP connection alive."""
        result = None
        done = asyncio.Event()

        # Periodically emit log pings until the job finishes.
        async def _ping_loop():
            try:
                session = mcp._mcp_server.request_context.session
            except (LookupError, AttributeError):
                return
            while not done.is_set():
                try:
                    await asyncio.wait_for(asyncio.shield(done.wait()), timeout=interval)
                except asyncio.TimeoutError:
                    pass
                if not done.is_set():
                    try:
                        await session.send_log_message(level="debug", data="downloading...", logger="import-web-file")
                    except Exception:
                        pass

        # Execute the wrapped coroutine and capture its result.
        async def _run():
            nonlocal result
            result = await coro
            done.set()

        await asyncio.gather(_run(), _ping_loop())
        return result

    # Register the file download tool.
    @mcp.tool()
    async def import_web_file(
        url: str,
        save_to: str = "downloads/",
        allowed_types: list[str] | None = None,
        max_size_mb: int = 50,
    ) -> dict:
        """
        Download a file from a URL and save it to the task workspace.

        RULES - read before calling:
        1. ONLY call this when you have confirmed the URL points to a real downloadable
           file (PDF, ZIP, image, etc.) - either from a search result badge (FILE /
           PDF FILE) or from a read_page hint (This URL points to a downloadable file).
        2. Do NOT call this speculatively or in a retry loop. If a URL is unknown,
           use web_search or read_page first to verify it exists and is downloadable.
        3. Do NOT call this for web pages, documentation sites, or GitHub repo URLs
           without a direct file extension (.zip, .pdf, etc.).
        4. One call per file. Do not retry the same URL more than once.

        save_to: subdirectory inside task/ to save the file (default: "downloads/")
        allowed_types: restrict by category - ["text", "media", "archive", "data"]
            text:    .pdf .docx .xlsx .csv .txt .md .json .xml .html
            media:   .mp3 .mp4 .wav .webm .mkv .jpg .jpeg .png .gif .webp
            archive: .zip .tar .gz .tar.gz .7z
            data:    .sqlite .db
        max_size_mb: abort download if file exceeds this size in MB (default: 50, hard cap: 50)

        Returns: {status, file, size_bytes, content_type, message}
        """
        return await _keepalive_download(
            download_file(
                url=url,
                project_dir=PROJECT_DIR,
                save_to=save_to,
                allowed_types=allowed_types,
                max_size_mb=min(max_size_mb, 50),
            )
        )
