# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import time

# Tool registration entry point.
def register_tools(mcp) -> None:
    """Register all Web Search MCP tools on the given FastMCP instance."""
    try:
        from .engine import (
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
            _prepare_results_with_previews,
            _proportional_merge,
            _proportional_allot,
            _parse_url_arg,
            _fetch_reddit_json,
            _fetch_with_camoufox,
            _fetch_with_curl_cffi,
            _fetch_curl_cffi_raw,
            _strip_html_to_text,
            _fetch_json_api,
            _fetch_via_wayback,
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
    except ImportError:
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
            _prepare_results_with_previews,
            _proportional_merge,
            _proportional_allot,
            _parse_url_arg,
            _fetch_reddit_json,
            _fetch_with_camoufox,
            _fetch_with_curl_cffi,
            _fetch_curl_cffi_raw,
            _strip_html_to_text,
            _fetch_json_api,
            _fetch_via_wayback,
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
    try:
        from .file_importer import download_file
    except ImportError:
        from file_importer import download_file
    try:
        from .overdrive import read_url_overdrive as _read_url_overdrive
    except ImportError:
        try:
            from overdrive import read_url_overdrive as _read_url_overdrive
        except ImportError:
            _read_url_overdrive = None
    from pathlib import Path
    from urllib.parse import urlparse

    # Overdrive config.
    try:
        from .. import config as _ws_config
    except (ImportError, ValueError):
        try:
            import config as _ws_config
        except ImportError:
            _ws_config = None

    # Source cache setup.
    _source_cache = None
    _page_fetcher = None
    try:
        if _ws_config and getattr(_ws_config, "SOURCE_CACHE_LOCAL_FIRST", False):
            try:
                from .source_cache import SourceCache
                from .page_fetcher import PageFetcher
            except ImportError:
                from source_cache import SourceCache
                from page_fetcher import PageFetcher
            _source_cache = SourceCache(
                db_path=getattr(_ws_config, "SOURCE_CACHE_DB", ""),
                default_ttl=getattr(_ws_config, "SOURCE_CACHE_TTL", 86400),
            )
            _page_fetcher = PageFetcher(
                cache=_source_cache,
                max_concurrent=getattr(_ws_config, "SOURCE_CACHE_FETCH_CONCURRENCY", 6),
                per_domain_rps=getattr(_ws_config, "SOURCE_CACHE_PER_DOMAIN_RPS", 1.0),
                timeout=getattr(_ws_config, "SOURCE_CACHE_FETCH_TIMEOUT", 10.0),
                store_raw_html=getattr(_ws_config, "SOURCE_CACHE_STORE_RAW_HTML", False),
            )
    except Exception as _sc_err:
        _debug_log(f"source cache init failed: {_sc_err}")

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

        try:
            overdrive_on = bool(getattr(_ws_config, "OVERDRIVE", False))
            od_batch_unlimited = bool(getattr(_ws_config, "WEB_SEARCH_OVERDRIVE_BATCH_UNLIMITED", True))
            od_batch_fetch_previews = bool(getattr(_ws_config, "WEB_SEARCH_OVERDRIVE_BATCH_FETCH_PREVIEWS", True))
            od_snippet_chars = int(getattr(_ws_config, "WEB_SEARCH_OVERDRIVE_SNIPPET_CHARS", 1200) or 1200)
            od_preview_limit = int(getattr(_ws_config, "WEB_SEARCH_OVERDRIVE_PREVIEW_LIMIT", 0) or 0)
            od_output_chars = int(getattr(_ws_config, "WEB_SEARCH_OVERDRIVE_OUTPUT_CHARS", 2400) or 2400)
            od_min_clean_chars = int(getattr(_ws_config, "WEB_SEARCH_OVERDRIVE_MIN_CLEAN_CHARS", 200) or 200)
        except Exception:
            overdrive_on = False
            od_batch_unlimited = True
            od_batch_fetch_previews = True
            od_snippet_chars = 1200
            od_preview_limit = 0
            od_output_chars = 2400
            od_min_clean_chars = 200

        # --- batch mode ---
        if isinstance(query, list):
            queries = [q.strip() for q in query if isinstance(q, str) and q.strip()][:10]
            if not queries:
                return ['{"error": "No queries provided"}']

            total_limit = limit * len(queries)
            if overdrive_on and od_batch_unlimited:
                total_limit = max(5, total_limit)
            else:
                total_limit = max(5, min(total_limit, 50))

            t0 = time.time()
            per_fetch = max(12, total_limit // max(len(queries), 1) + 6)

            # Search one query across both backends.
            async def _search_one_batch(q: str) -> list[SearchResult]:
                yacy_task = asyncio.wait_for(async_yacy_search(q, per_fetch), timeout=_YACY_SEARCH_TIMEOUT)
                ddgs_task  = asyncio.wait_for(async_ddgs_search(q, per_fetch), timeout=_DDGS_SEARCH_TIMEOUT)
                yr, dr = await asyncio.gather(yacy_task, ddgs_task, return_exceptions=True)
                yr = yr if isinstance(yr, list) else []
                dr = dr if isinstance(dr, list) else []
                return _proportional_merge(yr, dr, per_fetch)

            raw = await asyncio.gather(*[_search_one_batch(q) for q in queries], return_exceptions=True)
            per_query: list[list[SearchResult]] = [r if isinstance(r, list) else [] for r in raw]

            found_counts = [len(r) for r in per_query]
            allotments = _proportional_allot(found_counts, total_limit)

            ms = int((time.time() - t0) * 1000)
            total_returned = 0
            out_queries = []

            for q, results, allot in zip(queries, per_query, allotments):
                trimmed = results[:allot]
                previews = [""] * len(trimmed)
                if overdrive_on and od_batch_fetch_previews and trimmed:
                    effective_preview_limit = od_preview_limit if od_preview_limit > 0 else len(trimmed)
                    try:
                        trimmed, previews = await _prepare_results_with_previews(
                            trimmed,
                            q,
                            overrides={
                                "preview_limit": effective_preview_limit,
                                "output_chars": od_output_chars,
                                "min_clean_chars": od_min_clean_chars,
                            },
                        )
                    except Exception as e:
                        _debug_log(f"overdrive batch preview enrichment failed for '{q}': {e}")
                total_returned += len(trimmed)
                out_queries.append({
                    "query": q,
                    "count": len(trimmed),
                    "found": len(results),
                    "results": [
                        {
                            "title": r.title or "",
                            "url": r.url,
                            "snippet": (r.snippet or "")[:(od_snippet_chars if overdrive_on else 350)],
                            "preview": (previews[i] or "")[:od_output_chars] if i < len(previews) else "",
                            "engine": r.engine or "",
                        }
                        for i, r in enumerate(trimmed)
                    ],
                })

            out_blocks: list[str] = []
            for qdata in out_queries:
                q_hdr = "\n".join([
                    f"Web Search - {ms}ms",
                    f"Query   : {qdata['query']}",
                    f"Found   : {qdata['count']}  (YaCy: {sum(1 for r in qdata['results'] if 'yacy' in r['engine'].lower())}  DDGS: {sum(1 for r in qdata['results'] if 'yacy' not in r['engine'].lower())})",
                ])
                out_blocks.append(q_hdr)
                for i, r in enumerate(qdata["results"], 1):
                    lines = [
                        f"[{i}] {_badge_type(r['url'])} {_badge_engine(r['engine'])}",
                        f"Title   : {r['title'] or '-'}",
                        f"URL     : {r['url']}",
                        f"Snippet : {r['snippet'] or '-'}",
                    ]
                    if r.get("preview"):
                        lines.append(f"Preview : {r['preview']}")
                    out_blocks.append("\n".join(lines))
            return out_blocks

        # --- single query mode ---
        t0 = time.time()

        # Local-first: check source cache before hitting external search.
        _sc_min = int(getattr(_ws_config, "SOURCE_CACHE_MIN_LOCAL_RESULTS", 3) or 3)
        if _source_cache is not None:
            try:
                local_hits = _source_cache.search_local(query, limit=limit)
                if len(local_hits) >= _sc_min:
                    ms = int((time.time() - t0) * 1000)
                    hdr = "\n".join([
                        f"Web Search - {ms}ms  (from local cache)",
                        f"Query   : {query}",
                        f"Found   : {len(local_hits)}  (cached)",
                    ])
                    blocks = [hdr]
                    for i, hit in enumerate(local_hits, 1):
                        lines = [
                            f"[{i}] [CACHED]",
                            f"Title   : {hit.title or '-'}",
                            f"URL     : {hit.url}",
                            f"Preview : {hit.clean_text[:2400]}",
                        ]
                        blocks.append("\n".join(lines))
                    return blocks
            except Exception as e:
                _debug_log(f"source cache local search failed: {e}")

        yacy_task = asyncio.wait_for(async_yacy_search(query, limit), timeout=_YACY_SEARCH_TIMEOUT)
        ddgs_task  = asyncio.wait_for(async_ddgs_search(query, limit), timeout=_DDGS_SEARCH_TIMEOUT)

        yacy_res, ddgs_res = await asyncio.gather(yacy_task, ddgs_task, return_exceptions=True)

        yacy_res = yacy_res if isinstance(yacy_res, list) else []
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
        if ddgs_res:
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

        preview_overrides = None
        if overdrive_on:
            effective_preview_limit = od_preview_limit if od_preview_limit > 0 else len(results)
            preview_overrides = {
                "preview_limit": effective_preview_limit,
                "output_chars": od_output_chars,
                "min_clean_chars": od_min_clean_chars,
            }
        results, previews = await _prepare_results_with_previews(results, query, overrides=preview_overrides)

        # Format one result block for display.
        def _fmt_result(i: int, r: SearchResult, preview: str) -> str:
            lines = [
                f"[{i}] {_badge_type(r.url)} {_badge_engine(r.engine)}",
                f"Title   : {r.title or '-'}",
                f"URL     : {_short_url(r.url)}",
                f"Snippet : {(r.snippet or '-')[:(od_snippet_chars if overdrive_on else 400)]}",
            ]
            if preview:
                lines.append(f"Preview : {preview}")
            return "\n".join(lines)

        downloadable = [r for r in results if _is_downloadable_ext(r.url)]

        hdr = "\n".join([
            f"Web Search - {ms}ms",
            f"Query   : {query}",
            f"Found   : {len(results)}  (YaCy: {yn}  DDGS: {dn})",
        ])
        blocks = [hdr] + [_fmt_result(i, r, previews[i-1]) for i, r in enumerate(results, 1)]
        if downloadable:
            hint = "Downloadable files found - use import_web_file(url) to save to task workspace."
            blocks.append(hint)

        # Background: cache fetched pages and record query provenance.
        if _source_cache is not None and _page_fetcher is not None and results:
            try:
                _fetch_budget = int(getattr(_ws_config, "SOURCE_CACHE_FETCH_BUDGET", 10) or 10)
                urls_to_cache = [r.url for r in results if r.url and not _source_cache.is_fresh(r.url)]

                # Record query -> URL mappings.
                for rank, r in enumerate(results):
                    if r.url:
                        try:
                            _source_cache.record_query_source(query, r.url, rank)
                        except Exception:
                            pass

                # Background fetch + cache (non-blocking).
                if urls_to_cache:
                    asyncio.create_task(
                        _page_fetcher.fetch_and_cache(urls_to_cache, budget=_fetch_budget)
                    )

                # Background depth crawl on top domains.
                _depth_enabled = bool(getattr(_ws_config, "SOURCE_CACHE_DEPTH_ENABLED", False))
                if _depth_enabled:
                    try:
                        try:
                            from .depth_crawler import schedule_crawl as _schedule_crawl
                        except ImportError:
                            from depth_crawler import schedule_crawl as _schedule_crawl
                        _max_domains = int(getattr(_ws_config, "SOURCE_CACHE_DEPTH_MAX_DOMAINS", 3) or 3)
                        # Pick top domains from results.
                        _seen_domains = set()
                        _seed_urls = []
                        for r in results:
                            d = urlparse(r.url).netloc.lower()
                            if d and d not in _seen_domains and len(_seen_domains) < _max_domains:
                                _seen_domains.add(d)
                                _seed_urls.append(r.url)
                        if _seed_urls:
                            asyncio.create_task(_schedule_crawl(
                                cache=_source_cache,
                                seed_urls=_seed_urls,
                                allowed_domains=list(_seen_domains),
                                depth_limit=int(getattr(_ws_config, "SOURCE_CACHE_DEPTH_LIMIT", 1) or 1),
                                max_pages=int(getattr(_ws_config, "SOURCE_CACHE_DEPTH_MAX_PAGES", 20) or 20),
                                autothrottle_target=float(getattr(_ws_config, "SOURCE_CACHE_DEPTH_AUTOTHROTTLE", 2.0) or 2.0),
                                store_raw_html=bool(getattr(_ws_config, "SOURCE_CACHE_STORE_RAW_HTML", False)),
                            ))
                    except Exception as e:
                        _debug_log(f"depth crawl schedule failed: {e}")
            except Exception as e:
                _debug_log(f"source cache background tasks failed: {e}")

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

        save=True: save each page as JSON to _sandbox/pages/<slug>.json in the sandbox workspace.
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

        # Fetch one URL and return (processed_text, raw_html_or_none).
        async def _fetch_and_process(u: str) -> tuple[str, str | None]:
            if _is_youtube(u):
                loop = asyncio.get_running_loop()
                text = await loop.run_in_executor(None, _youtube_transcript, u)
                return text, None
            if _is_skippable(u):
                if _is_downloadable_ext(u):
                    return (
                        f"Source: {u}\n"
                        f"This URL points to a downloadable file, not a web page.\n"
                        f"Use import_web_file(\"{u}\") to save it to the task workspace."
                    ), None
                return f"Source: {u}\nSkipped: domain is blocked or unsupported.", None

            _host = urlparse(u).netloc.lower().removeprefix("www.")
            if _host in ("reddit.com", "old.reddit.com") or _host.endswith(".reddit.com"):
                try:
                    text = await _fetch_reddit_json(u)
                    if text.strip():
                        return f"Source: {u}\n\n{text}", None
                except Exception as e:
                    _debug_log(f"reddit_json failed for {u}: {e}")
                # .json API blocked — try overdrive (Camoufox/Patchright can handle Reddit)
                if (
                    _read_url_overdrive is not None
                    and _ws_config is not None
                    and getattr(_ws_config, "OVERDRIVE", False)
                ):
                    try:
                        text = await _read_url_overdrive(
                            u,
                            human_behavior=getattr(_ws_config, "OVERDRIVE_HUMAN_BEHAVIOR", True),
                            ocr_fallback=False,
                            parallel_timeout=getattr(_ws_config, "OVERDRIVE_PARALLEL_TIMEOUT", 20.0),
                            ocr_timeout=getattr(_ws_config, "OVERDRIVE_OCR_TIMEOUT", 30.0),
                            browser_start_delay=getattr(_ws_config, "OVERDRIVE_BROWSER_START_DELAY", 0.75),
                            browser_concurrency=getattr(_ws_config, "OVERDRIVE_BROWSER_CONCURRENCY", 2),
                            browser_fanout=getattr(_ws_config, "OVERDRIVE_BROWSER_FANOUT", 4),
                            browser_idle_timeout=getattr(_ws_config, "OVERDRIVE_BROWSER_IDLE_TIMEOUT", 30.0),
                        )
                        if text.strip():
                            return f"Source: {u}\n[OVERDRIVE]\n\n{text[:12000]}", None
                    except Exception as e:
                        _debug_log(f"overdrive reddit failed for {u}: {e}")
                return f"Source: {u}\nError: Reddit fetch failed.", None

            reg = _domain_registry
            method = "http"
            tier = "unknown"
            json_api_hint = None
            try_preview_bot = False
            if reg is not None:
                info = reg.lookup(u)
                method = info.method
                tier = info.tier
                json_api_hint = info.json_api_hint
                try_preview_bot = bool(getattr(info, "try_preview_bot", False))
            mimic_user_agent = bool(getattr(_ws_config, "MIMIC_USER_AGENT", True))

            if try_preview_bot and mimic_user_agent:
                try:
                    try:
                        from preview_bot_fetcher import probe_with_preview_bots as _probe_with_preview_bots
                    except ImportError:
                        from .preview_bot_fetcher import probe_with_preview_bots as _probe_with_preview_bots  # type: ignore
                    text = await _probe_with_preview_bots(u, timeout=12)
                    if text.strip() and not _is_antibot(text):
                        return f"Source: {u}\n[PREVIEW_BOT]\n\n{text[:12000]}", None
                except Exception as e:
                    _debug_log(f"preview_bot failed for {u}: {e}")

            if method == "json_api":
                api_url = json_api_hint or u
                if "<query>" in api_url or "<q>" in api_url:
                    from urllib.parse import urlparse as _up, unquote as _uq
                    path = _uq(_up(u).path).strip("/").split("/")[-1]
                    api_url = api_url.replace("<query>", path).replace("<q>", path)
                try:
                    text = await _fetch_json_api(api_url)
                    return f"Source: {u}\nAPI: {api_url}\n\n{text}", None
                except Exception as e:
                    return f"Source: {u}\nError: JSON API fetch failed: {e}", None

            try:
                from ingest.router import ingest_router
                b = await ingest_router.ingest(u)
                return f"Source: {u}\n\n{b.markdown_content}", None
            except ImportError:
                pass
            except Exception as e:
                _debug_log(f"read_page ingest_router error for {u}: {e}")

            # Overdrive mode: multi-method staggered race.
            if (
                _read_url_overdrive is not None
                and _ws_config is not None
                and getattr(_ws_config, "OVERDRIVE", False)
            ):
                try:
                    text = await _read_url_overdrive(
                        u,
                        human_behavior=getattr(_ws_config, "OVERDRIVE_HUMAN_BEHAVIOR", True),
                        ocr_fallback=getattr(_ws_config, "OVERDRIVE_OCR_FALLBACK", True),
                        parallel_timeout=getattr(_ws_config, "OVERDRIVE_PARALLEL_TIMEOUT", 20.0),
                        ocr_timeout=getattr(_ws_config, "OVERDRIVE_OCR_TIMEOUT", 30.0),
                        browser_start_delay=getattr(_ws_config, "OVERDRIVE_BROWSER_START_DELAY", 0.75),
                        browser_concurrency=getattr(_ws_config, "OVERDRIVE_BROWSER_CONCURRENCY", 2),
                        browser_fanout=getattr(_ws_config, "OVERDRIVE_BROWSER_FANOUT", 4),
                        browser_idle_timeout=getattr(_ws_config, "OVERDRIVE_BROWSER_IDLE_TIMEOUT", 30.0),
                    )
                    if text.strip():
                        return f"Source: {u}\n[OVERDRIVE]\n\n{text[:12000]}", None
                    return f"Source: {u}\nError: All overdrive methods failed.", None
                except Exception as e:
                    _debug_log(f"overdrive failed for {u}: {e}")
                    return f"Source: {u}\nError: Overdrive fetch failed: {e}", None

            if method == "camoufox" or tier == "fortress":
                try:
                    text = await _fetch_with_camoufox(u)
                    if text.strip():
                        return f"Source: {u}\n\n{text}", None
                except Exception as e:
                    _debug_log(f"camoufox failed for {u}: {e}")
                    return f"Source: {u}\nError: Failed to load (camoufox): {e}", None

            if tier == "hardened":
                try:
                    raw_html = await _fetch_curl_cffi_raw(u)
                    text = _strip_html_to_text(raw_html)
                    return f"Source: {u}\n\n{text[:12000]}", raw_html
                except Exception as e:
                    return f"Source: {u}\nError: curl_cffi fetch failed: {e}", None

            try:
                import httpx, re
                raw_html = None
                async with httpx.AsyncClient(follow_redirects=True, timeout=15) as c:
                    r = await c.get(u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                    r.raise_for_status()
                    raw_html = r.text
                    stripped = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', raw_html, flags=re.IGNORECASE | re.DOTALL)
                    text = re.sub(r"\s{2,}", "\n", re.sub(r"<[^>]+>", " ", stripped)).strip()
                if _is_antibot(text):
                    try:
                        ab_raw = await _fetch_curl_cffi_raw(u)
                        text = _strip_html_to_text(ab_raw)
                        raw_html = ab_raw
                    except Exception:
                        pass
                    # Wayback Machine fallback when live site is blocked — only in overdrive mode.
                    if not text or _is_antibot(text):
                        _overdrive_on = bool(getattr(_ws_config, "OVERDRIVE", False))
                        if _overdrive_on:
                            _wb_timeout = int(getattr(_ws_config, "WAYBACK_TIMEOUT", 30))
                            try:
                                wb_text = await _fetch_via_wayback(u, timeout=_wb_timeout)
                                if wb_text and not _is_antibot(wb_text):
                                    return f"Source: {u}\n[WAYBACK]\n\n{wb_text[:12000]}", None
                            except Exception:
                                pass
                        return f"Source: {u}\nError: Blocked by anti-bot.", None
                return f"Source: {u}\n\n{text[:12000]}", raw_html
            except Exception as e:
                try:
                    fb_raw = await _fetch_curl_cffi_raw(u)
                    text = _strip_html_to_text(fb_raw)
                    if not _is_antibot(text):
                        return f"Source: {u}\n\n{text[:12000]}", fb_raw
                except Exception:
                    pass
                # Wayback Machine as last resort — only in overdrive mode.
                _overdrive_on = bool(getattr(_ws_config, "OVERDRIVE", False))
                if _overdrive_on:
                    _wb_timeout = int(getattr(_ws_config, "WAYBACK_TIMEOUT", 30))
                    try:
                        wb_text = await _fetch_via_wayback(u, timeout=_wb_timeout)
                        if wb_text and not _is_antibot(wb_text):
                            return f"Source: {u}\n[WAYBACK]\n\n{wb_text[:12000]}", None
                    except Exception:
                        pass
                return f"Source: {u}\nError: Failed to load: {e}", None

        # Normalize and return page content for non-save callers.
        async def _process_single(u: str) -> str:
            text, raw_html = await _fetch_and_process(u)
            if "Error:" in text or not text.strip():
                return text
            try:
                try:
                    from page_normalizer import normalize_page
                except ImportError:
                    from .page_normalizer import normalize_page  # type: ignore
                loop = asyncio.get_running_loop()
                capped_text = text[:20000] if text else text
                clean = await asyncio.wait_for(
                    loop.run_in_executor(
                        None, lambda: normalize_page(url=u, raw_html=raw_html, fallback_text=capped_text)
                    ),
                    timeout=8.0,
                )
                if clean:
                    body = clean.split("---", 1)[-1].strip()
                    if len(body) > 80:
                        return clean
            except asyncio.TimeoutError:
                _debug_log(f"page_normalizer timeout for {u}")
            except Exception as e:
                _debug_log(f"page_normalizer failed for {u}: {e}")
            return text

        if save:
            # Read and persist one URL as JSON + clean markdown.
            async def _save_single(u: str) -> str:
                content, raw_html = await _fetch_and_process(u)
                if "Error:" in content:
                    return content
                slug = _url_to_slug(u)

                # 1. Raw JSON (unchanged format)
                dest_raw = pages_dir / f"{slug}.json"
                payload = _json.dumps(
                    {"url": u, "content": content.splitlines()},
                    ensure_ascii=False, indent=2
                )
                dest_raw.write_text(payload, encoding="utf-8")

                # 2. Clean markdown
                dest_clean = pages_dir / f"{slug}.clean.md"
                try:
                    try:
                        from page_normalizer import normalize_page
                    except ImportError:
                        from .page_normalizer import normalize_page  # type: ignore
                    clean_md = normalize_page(url=u, raw_html=raw_html, fallback_text=content)
                    dest_clean.write_text(clean_md, encoding="utf-8")
                except Exception as e:
                    import traceback as _tb
                    _debug_log(f"page_normalizer failed for {u}: {e}\n{_tb.format_exc()}")

                saved = f"Saved: _sandbox/pages/{dest_raw.name}"
                if dest_clean.exists():
                    saved += f" + {dest_clean.name}"
                return saved

            tasks = [_save_single(u) for u in urls]
        else:
            tasks = [_process_single(u) for u in urls]

        results = await asyncio.gather(*tasks)
        if save:
            saved_json = [r for r in results if r and ".json" in r and "Error:" not in r]
            saved_md = [r for r in results if r and ".clean.md" in r]
            summary = f"Done: {len(saved_json)} page(s) saved."
            if saved_md:
                summary += f" Clean markdown created for {len(saved_md)} page(s)."
            elif saved_json:
                summary += " (normalizer unavailable — raw JSON only)"
            return list(results) + [summary]
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
        import uuid
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

            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-u", str(script), query, "--depth", depth, "--id", task_id,
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

        save_to: subdirectory inside _sandbox/ to save the file (default: "downloads/")
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
