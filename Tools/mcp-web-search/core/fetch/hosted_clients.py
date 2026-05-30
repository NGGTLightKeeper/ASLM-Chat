# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from pathlib import Path

from core.models.search import SearchResult
from core.config.api_keys import load_api_keys
from core.fetch.engine_stats import Observation
from core.cache.hosted_cache import get_hosted_cache, query_ttl, NEGATIVE_TTL

logger = logging.getLogger("core.fetch.hosted_clients")

# ---------------------------------------------------------------------------
# Tavily search depth
# ---------------------------------------------------------------------------
# "basic"    — fast, returns ~200-400 char content snippets (1 credit/search)
# "advanced" — Tavily crawls and returns raw_content (full page text,
#              2 credits/search).  raw_content is fed into SourceCache so
#              the preview pipeline (trafilatura → BM25 → GliNER) runs on it
#              exactly as it would on a directly fetched page — no pre-truncation.
TAVILY_SEARCH_DEPTH: str = "advanced"

import atexit
import threading

_pool: Optional[ThreadPoolExecutor] = None
_pool_lock = threading.Lock()


# Thread pool for sync hosted API calls.
def _get_pool() -> ThreadPoolExecutor:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                p = ThreadPoolExecutor(max_workers=8, thread_name_prefix="hosted")
                atexit.register(p.shutdown, wait=False)
                _pool = p
    return _pool


# ---------------------------------------------------------------------------
# Shared SourceCache — pre-populate with hosted provider content so that
# _fetch_preview_one gets a cache-hit and the normal extraction pipeline
# (trafilatura → BM25 → GliNER) runs on the full text without re-fetching.
# Points to the same DB file as services/web_search.py uses.
# ---------------------------------------------------------------------------

# core/fetch/ → core/ → mcp-web-search/ → tmp/source_cache.db
# Shared with services.web_search: persistent cache lives under _cache/.
_PAGE_CACHE_PATH = Path(__file__).resolve().parents[2] / "_cache" / "source_cache.db"

_page_cache = None
_page_cache_lock = threading.Lock()


# Shared SourceCache for Tavily raw_content pre-population.
def _get_page_cache():
    global _page_cache
    if _page_cache is None:
        with _page_cache_lock:
            if _page_cache is None:
                from core.cache.source_cache import SourceCache
                _page_cache = SourceCache(str(_PAGE_CACHE_PATH))
    return _page_cache


# Wrap plain text in minimal HTML for SourceCache / preview pipeline.
def _wrap_as_html(text: str) -> str:
    import html as _html
    return f"<html><body><article>{_html.escape(text)}</article></body></html>"


# Stable hash of top-5 URLs for router telemetry.
def _result_hash(results: list[SearchResult]) -> int:
    urls = "||".join(r.url for r in results[:5])
    return int(hashlib.md5(urls.encode()).hexdigest()[:8], 16)


_ENGINE_KEY_ATTR: dict[str, str] = {
    "tavily":  "tavily_api_key",
    "brave":   "brave_api_key",
    "bing":    "bing_api_key",
    "serpapi": "serpapi_api_key",
}

HOSTED_ENGINES: list[str] = list(_ENGINE_KEY_ATTR)


# Return hosted engine names that have an API key configured.
def available_hosted_engines() -> list[str]:
    keys = load_api_keys().search
    return [
        name for name, attr in _ENGINE_KEY_ATTR.items()
        if getattr(keys, attr, None)
    ]


# Tavily Search API (POST /search); advanced depth returns raw_content.
class TavilyClient:

    BASE_URL = "https://api.tavily.com/search"
    TIMEOUT = 15.0

    _DAYS_MAP = {"d": 1, "w": 7, "m": 30, "y": 365}

    # POST search; returns results plus url→full_text map for SourceCache.
    def search_with_content(
        self,
        query: str,
        max_results: int = 10,
        *,
        timelimit: Optional[str] = None,
        search_depth: str = TAVILY_SEARCH_DEPTH,
    ) -> tuple[list[SearchResult], dict[str, str]]:
        import requests

        api_key = load_api_keys().search.tavily_api_key
        if not api_key:
            return [], {}

        use_advanced = search_depth == "advanced"
        payload: dict = {
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_answer": False,
            "include_raw_content": use_advanced,
        }
        if timelimit and timelimit in self._DAYS_MAP:
            payload["days"] = self._DAYS_MAP[timelimit]

        try:
            resp = requests.post(self.BASE_URL, json=payload, timeout=self.TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("[tavily] request failed: %s", exc)
            return [], {}

        results: list[SearchResult] = []
        content_map: dict[str, str] = {}

        for item in data.get("results", []):
            url = item.get("url") or ""
            if not url:
                continue
            title = item.get("title") or ""
            # content = short summary (always present)
            # raw_content = full page text (only when include_raw_content=True)
            content = item.get("content") or ""
            raw_content = item.get("raw_content") or ""

            # snippet: short version used by triage scoring
            snippet = content[:2000]

            # full_text: everything Tavily has — fed into SourceCache as-is.
            # Truncation/compression is the pipeline's job (BM25 / GliNER).
            full_text = raw_content or content
            if full_text:
                content_map[url] = full_text

            results.append(SearchResult(
                url=url,
                title=title,
                snippet=snippet,
                engine="hosted:tavily",
                published_date=str(item.get("published_date") or ""),
            ))

        return results, content_map

    # Search without returning the raw_content side map.
    def search(
        self,
        query: str,
        max_results: int = 10,
        *,
        timelimit: Optional[str] = None,
        search_depth: str = TAVILY_SEARCH_DEPTH,
    ) -> list[SearchResult]:
        results, _ = self.search_with_content(
            query, max_results, timelimit=timelimit, search_depth=search_depth,
        )
        return results


# Brave Search API (GET /res/v1/web/search).
class BraveClient:

    BASE_URL = "https://api.search.brave.com/res/v1/web/search"
    TIMEOUT = 10.0

    _FRESHNESS_MAP = {"d": "pd", "w": "pw", "m": "pm", "y": "py"}

    # GET web search results.
    def search(
        self,
        query: str,
        max_results: int = 10,
        *,
        timelimit: Optional[str] = None,
    ) -> list[SearchResult]:
        import requests

        api_key = load_api_keys().search.brave_api_key
        if not api_key:
            return []

        params: dict = {"q": query, "count": min(max_results, 20)}
        if timelimit and timelimit in self._FRESHNESS_MAP:
            params["freshness"] = self._FRESHNESS_MAP[timelimit]

        try:
            resp = requests.get(
                self.BASE_URL,
                params=params,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                },
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("[brave] request failed: %s", exc)
            return []

        out: list[SearchResult] = []
        for item in data.get("web", {}).get("results", []):
            url = item.get("url") or ""
            title = item.get("title") or ""
            snippet = item.get("description") or ""
            if not url:
                continue
            out.append(SearchResult(
                url=url,
                title=title,
                snippet=snippet[:2000],
                engine="hosted:brave",
                published_date=str(item.get("page_age") or item.get("age") or ""),
            ))
        return out


# Bing Web Search API v7.
class BingClient:

    BASE_URL = "https://api.bing.microsoft.com/v7.0/search"
    TIMEOUT = 10.0

    _FRESHNESS_MAP = {"d": "Day", "w": "Week", "m": "Month"}

    # GET web search results.
    def search(
        self,
        query: str,
        max_results: int = 10,
        *,
        timelimit: Optional[str] = None,
    ) -> list[SearchResult]:
        import requests

        api_key = load_api_keys().search.bing_api_key
        if not api_key:
            return []

        params: dict = {"q": query, "count": min(max_results, 50), "responseFilter": "Webpages"}
        if timelimit and timelimit in self._FRESHNESS_MAP:
            params["freshness"] = self._FRESHNESS_MAP[timelimit]

        try:
            resp = requests.get(
                self.BASE_URL,
                params=params,
                headers={"Ocp-Apim-Subscription-Key": api_key},
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("[bing] request failed: %s", exc)
            return []

        out: list[SearchResult] = []
        for item in data.get("webPages", {}).get("value", []):
            url = item.get("url") or ""
            title = item.get("name") or ""
            snippet = item.get("snippet") or ""
            if not url:
                continue
            out.append(SearchResult(
                url=url,
                title=title,
                snippet=snippet[:2000],
                engine="hosted:bing",
                published_date=str(item.get("datePublished") or item.get("dateLastCrawled") or ""),
            ))
        return out


# SerpAPI Google engine (GET /search.json).
class SerpApiClient:

    BASE_URL = "https://serpapi.com/search.json"
    TIMEOUT = 12.0

    _TBS_MAP = {"d": "qdr:d", "w": "qdr:w", "m": "qdr:m", "y": "qdr:y"}

    # GET Google organic results via SerpAPI.
    def search(
        self,
        query: str,
        max_results: int = 10,
        *,
        timelimit: Optional[str] = None,
    ) -> list[SearchResult]:
        import requests

        api_key = load_api_keys().search.serpapi_api_key
        if not api_key:
            return []

        params: dict = {
            "q": query,
            "num": min(max_results, 100),
            "engine": "google",
            "api_key": api_key,
            "output": "json",
        }
        if timelimit and timelimit in self._TBS_MAP:
            params["tbs"] = self._TBS_MAP[timelimit]

        try:
            resp = requests.get(
                self.BASE_URL,
                params=params,
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("[serpapi] request failed: %s", exc)
            return []

        out: list[SearchResult] = []
        for item in data.get("organic_results", []):
            url = item.get("link") or ""
            title = item.get("title") or ""
            snippet = item.get("snippet") or ""
            if not url:
                continue
            out.append(SearchResult(
                url=url,
                title=title,
                snippet=snippet[:2000],
                engine="hosted:serpapi",
                published_date=str(item.get("date") or ""),
            ))
        return out


_API_QUERY_STRIP_RE = re.compile(r'[\[\]*\\]')


# Strip characters that break hosted API parsers ([ ] * \ unbalanced quotes).
def _sanitize_query_for_api(query: str) -> str:
    query = _API_QUERY_STRIP_RE.sub("", query)
    if query.count('"') % 2 != 0:
        query = query.replace('"', "")
    return " ".join(query.split())


_CLIENTS: dict[str, object] = {
    "tavily":  TavilyClient(),
    "brave":   BraveClient(),
    "bing":    BingClient(),
    "serpapi": SerpApiClient(),
}


# Sync dispatch with HostedSearchCache get → API → set.
def search_with_hosted(
    engine: str,
    query: str,
    max_results: int = 10,
    *,
    timelimit: Optional[str] = None,
    query_type: str = "general",
    bypass_cache: bool = False,
) -> list[SearchResult]:
    client = _CLIENTS.get(engine)
    if client is None:
        logger.error("[hosted] unknown engine: %s", engine)
        return []

    cache = get_hosted_cache()

    if not bypass_cache:
        cached = cache.get(engine, query, timelimit)
        if cached is not None:
            logger.debug("[%s] cache hit (%d results)", engine, len(cached))
            return cached

    results = client.search(_sanitize_query_for_api(query), max_results, timelimit=timelimit)  # type: ignore[union-attr]

    ttl = NEGATIVE_TTL if not results else query_ttl(query_type)
    cache.set(engine, query, results, timelimit=timelimit, ttl=ttl)

    return results


# Async hosted search in thread; Tavily pre-populates SourceCache with raw_content.
async def async_hosted_search(
    engine: str,
    query: str,
    max_results: int = 10,
    *,
    timelimit: Optional[str] = None,
    query_type: str = "general",
) -> list[SearchResult]:
    from core.fetch.engine_router import get_router

    loop = asyncio.get_running_loop()
    t0 = time.perf_counter()

    results: list[SearchResult] = []
    try:
        search_cache = get_hosted_cache()

        if engine == "tavily":
            # 1. Check search result cache first.
            cached = search_cache.get("tavily", query, timelimit)
            if cached is not None:
                logger.debug("[tavily] search cache hit (%d results)", len(cached))
                return cached

            # 2. Fetch from Tavily (includes full raw_content).
            tavily_client: TavilyClient = _CLIENTS["tavily"]  # type: ignore[assignment]
            results, content_map = await loop.run_in_executor(
                _get_pool(),
                lambda: tavily_client.search_with_content(
                    query, max_results, timelimit=timelimit,
                ),
            )

            # 3. Pre-populate SourceCache with full page content so that
            #    _fetch_preview_one() gets a cache-hit and trafilatura/BM25
            #    run on the full text without a second HTTP fetch.
            if content_map:
                page_cache = _get_page_cache()
                for url, full_text in content_map.items():
                    try:
                        title = next((r.title for r in results if r.url == url), "")
                        page_cache.cache_page(
                            url, title,
                            clean_text="",
                            raw_html=_wrap_as_html(full_text),
                        )
                    except Exception:
                        pass
                logger.debug(
                    "[tavily] pre-populated page cache for %d/%d urls",
                    len(content_map), len(results),
                )

            # 4. Save search results to search result cache with proper TTL.
            search_cache.set(
                "tavily", query, results,
                timelimit=timelimit,
                ttl=NEGATIVE_TTL if not results else query_ttl(query_type),
            )

        else:
            # For non-Tavily engines search_with_hosted handles its own caching.
            results = await loop.run_in_executor(
                _get_pool(),
                lambda: search_with_hosted(
                    engine, query, max_results,
                    timelimit=timelimit,
                    query_type=query_type,
                ),
            )
    except Exception as exc:
        logger.warning("[%s] async_hosted_search failed: %s", engine, exc)
        results = []

    latency = time.perf_counter() - t0
    obs = Observation(
        ts=time.time(),
        latency=latency,
        success=bool(results),
        result_count=len(results),
        quality_pass=len(results) >= 3,
        result_hash=_result_hash(results),
    )
    try:
        get_router().record(engine, obs)
    except Exception:
        pass  # telemetry is best-effort

    logger.debug(
        "[%s] hosted search done: results=%d latency=%.2fs",
        engine, len(results), latency,
    )
    return results
