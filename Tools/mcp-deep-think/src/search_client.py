# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse, urlunparse

import httpx
import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from .config import settings

logger = logging.getLogger(__name__)


# Shared search integrations
_DR_SRC = (
    Path(__file__).resolve().parent.parent.parent
    / "mcp-web-search"
    / "deep-research"
)
_async_ddgs_search_fn = None

if _DR_SRC.exists():
    deep_research_root = str(_DR_SRC)
    if deep_research_root not in sys.path:
        sys.path.insert(0, deep_research_root)
    try:
        from src.ddgs_client import async_ddgs_search as _async_ddgs_search_fn
    except ImportError as exc:  # pragma: no cover - depends on local env
        logger.debug("Shared DDGS client not available: %s", exc)


try:
    from ddgs import DDGS as _DDGS_CLS
except ImportError:
    try:
        from duckduckgo_search import DDGS as _DDGS_CLS
    except ImportError:  # pragma: no cover - environment specific
        _DDGS_CLS = None


# Search result containers

# Hold one normalized search result
class SearchResult:
    def __init__(
        self,
        title: str,
        url: str,
        content: str,
        engine: str = "",
        page_text: str = "",
    ):
        self.title = title
        self.url = url
        self.content = content
        self.engine = engine
        self.domain = urlparse(url).netloc
        self.page_text = page_text

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "domain": self.domain,
            "engine": self.engine,
            "page_text": self.page_text,
        }

    def model_dump(self) -> dict:
        return self.to_dict()


# Cache entries

# Keep cached results with an expiration timestamp
class CacheEntry:
    def __init__(self, results: list[SearchResult], ttl_seconds: int):
        self.results = results
        self.expires_at = datetime.now() + timedelta(seconds=ttl_seconds)

    def is_valid(self) -> bool:
        return datetime.now() < self.expires_at


# Search client

# Perform bounded search and lightweight page reads for agents
class SearchClient:
    UNTRUSTED_DOMAINS = {
        "reddit.com",
        "twitter.com",
        "x.com",
        "facebook.com",
        "tiktok.com",
        "instagram.com",
        "quora.com",
        "pinterest.com",
    }
    YACY_URL = "http://localhost:8090"
    YACY_USER = "admin"
    YACY_PASS = "admin123"
    SKIP_EXTS = (".pdf", ".mp4", ".mp3", ".avi", ".mov", ".zip", ".exe", ".dmg")

    def __init__(
        self,
        max_concurrent: Optional[int] = None,
        cache_ttl: Optional[int] = None,
    ):
        """Initialize concurrency, TTL, and the shared HTTP client handle."""

        self.max_concurrent = max_concurrent or settings.max_concurrent_search_requests
        self.cache_ttl = cache_ttl or settings.search_cache_ttl_seconds
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._cache: dict[str, CacheEntry] = {}
        self._http_client: httpx.AsyncClient | None = None


    # Client helpers
    async def _get_http_client(self) -> httpx.AsyncClient:
        """Create the shared async HTTP client on first use."""

        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(connect=8.0, read=15.0, write=15.0, pool=10.0),
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
        return self._http_client

    def _cache_key(self, query: str, lang: str) -> str:
        """Build a stable cache key for a query and language pair."""

        return hashlib.md5(f"{query}:{lang}".encode()).hexdigest()


    # Result normalization
    def _deduplicate(self, results: list[SearchResult]) -> list[SearchResult]:
        """Drop duplicate URLs and cap repeated domains."""

        seen_urls: set[str] = set()
        domain_counts: dict[str, int] = {}
        deduped: list[SearchResult] = []
        for result in results:
            if result.url in seen_urls:
                continue
            domain = result.domain.lower().replace("www.", "")
            if domain_counts.get(domain, 0) >= 2:
                continue
            seen_urls.add(result.url)
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            deduped.append(result)
        return deduped

    def _sort_by_trust(self, results: list[SearchResult]) -> list[SearchResult]:
        """Move likely trusted domains ahead of social or user-generated sources."""

        trusted: list[SearchResult] = []
        untrusted: list[SearchResult] = []
        for result in results:
            domain = result.domain.lower().replace("www.", "")
            if any(untrusted_domain in domain for untrusted_domain in self.UNTRUSTED_DOMAINS):
                untrusted.append(result)
            else:
                trusted.append(result)
        return trusted + untrusted

    def _convert_ddgs(self, raw_items: list) -> list[SearchResult]:
        """Normalize DDGS payloads into SearchResult instances."""

        converted: list[SearchResult] = []
        for item in raw_items:
            if hasattr(item, "url"):
                url = item.url
                title = getattr(item, "title", "")
                content = getattr(item, "snippet", "") or getattr(item, "body", "")
                engine = getattr(item, "engine", "ddgs")
            else:
                url = item.get("href", "") or item.get("url", "")
                title = item.get("title", "")
                content = item.get("body", "") or item.get("snippet", "")
                engine = item.get("engine", "ddgs")
            if url:
                converted.append(SearchResult(title=title, url=url, content=content[:500], engine=engine))
        return converted


    # Search backends
    async def _search_ddgs(self, query: str, limit: int, lang: str) -> list[SearchResult]:
        """Query DDGS through the shared helper or local client."""

        try:
            if _async_ddgs_search_fn is not None:
                raw = await _async_ddgs_search_fn(query=query, max_results=limit * 2, lang=lang)
                return self._convert_ddgs(raw)
            if _DDGS_CLS is None:
                return []

            def _sync_search():
                ddgs = _DDGS_CLS(timeout=10)
                return ddgs.text(query, max_results=limit * 2) or []

            raw = await asyncio.get_running_loop().run_in_executor(None, _sync_search)
            return self._convert_ddgs(raw)
        except Exception as exc:
            logger.warning("DDGS search failed: %s", exc)
            return []

    async def _search_yacy(self, query: str, limit: int) -> list[SearchResult]:
        """Query the local YaCy node and normalize the response."""

        def _sync_search() -> list[SearchResult]:
            params = {
                "query": query,
                "resource": "global",
                "maximumRecords": limit,
                "verify": "false",
                "contentdom": "text",
            }
            auth = HTTPBasicAuth(self.YACY_USER, self.YACY_PASS)
            digest = HTTPDigestAuth(self.YACY_USER, self.YACY_PASS)
            try:
                response = requests.get(f"{self.YACY_URL}/yacysearch.json", params=params, auth=auth, timeout=8)
                if response.status_code == 401:
                    response = requests.get(f"{self.YACY_URL}/yacysearch.json", params=params, auth=digest, timeout=8)
                response.raise_for_status()
                data = response.json()
            except Exception:
                return []

            output: list[SearchResult] = []
            for item in (data.get("channels") or [{}])[0].get("items", []):
                link = item.get("link", "")
                if not link:
                    continue
                output.append(
                    SearchResult(
                        title=html.unescape(item.get("title", "")),
                        url=link,
                        content=html.unescape(item.get("description", ""))[:500],
                        engine="yacy_global",
                    )
                )
            return output

        return await asyncio.get_running_loop().run_in_executor(None, _sync_search)

    def _merge_sources(self, yacy_results: list[SearchResult], ddgs_results: list[SearchResult], limit: int) -> list[SearchResult]:
        """Blend YaCy and DDGS results proportionally into one shortlist."""

        y_count = len(yacy_results)
        d_count = len(ddgs_results)
        if y_count == 0:
            return ddgs_results[:limit]
        if d_count == 0:
            return yacy_results[:limit]
        total = y_count + d_count
        y_take = max(1, round(limit * y_count / total))
        d_take = limit - y_take
        if y_take > y_count:
            y_take = y_count
            d_take = min(limit - y_take, d_count)
        elif d_take > d_count:
            d_take = d_count
            y_take = min(limit - d_take, y_count)
        y_slice = yacy_results[:y_take]
        d_slice = ddgs_results[:d_take]
        merged = [item for pair in zip(y_slice, d_slice) for item in pair]
        merged += y_slice[len(d_slice):] + d_slice[len(y_slice):]
        return merged[:limit]


    # Read heuristics
    def _is_skippable(self, url: str) -> bool:
        """Return whether the URL points to a format we do not lightweight-read."""

        lowered = url.lower()
        if any(lowered.endswith(ext) for ext in self.SKIP_EXTS):
            return True
        return False

    def _is_youtube(self, url: str) -> bool:
        """Return whether the URL belongs to YouTube."""

        host = urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")
        return host in {"youtube.com", "youtu.be"}

    def _youtube_video_id(self, url: str) -> str | None:
        """Extract a YouTube video id from common URL formats."""

        for pattern in (
            r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})",
        ):
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _extract_youtube_transcript_sync(self, url: str) -> str:
        """Fetch a YouTube transcript through the API or subtitle fallback."""

        video_id = self._youtube_video_id(url)
        if not video_id:
            return ""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            api = YouTubeTranscriptApi()
            for lang in ("en", "ru", "uk", "de", "fr", "es"):
                try:
                    transcript = api.fetch(video_id, languages=[lang])
                    text_parts = [getattr(entry, "text", "") if not isinstance(entry, dict) else entry.get("text", "") for entry in transcript]
                    text = " ".join(part for part in text_parts if part)
                    if text:
                        return text
                except Exception:
                    continue
        except Exception:
            pass

        try:
            import glob
            import os
            import tempfile
            import yt_dlp

            with tempfile.TemporaryDirectory() as tmpdir:
                opts = {
                    "skip_download": True,
                    "writesubtitles": True,
                    "writeautomaticsub": True,
                    "subtitleslangs": ["en", "ru"],
                    "subtitlesformat": "vtt",
                    "outtmpl": os.path.join(tmpdir, "sub"),
                    "quiet": True,
                    "no_warnings": True,
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                files = glob.glob(os.path.join(tmpdir, "sub*.vtt"))
                if not files:
                    return ""
                payload = Path(files[0]).read_text(encoding="utf-8", errors="ignore")
                lines = []
                for line in payload.splitlines():
                    if not line or line.startswith("WEBVTT") or "-->" in line or line.isdigit():
                        continue
                    lines.append(line.strip())
                return " ".join(lines)
        except Exception:
            return ""

    async def _fetch_reddit_json(self, url: str) -> str:
        """Fetch a Reddit thread via the JSON endpoint and summarize the post body."""

        loop = asyncio.get_running_loop()
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        if not path.endswith(".json"):
            path += ".json"
        json_url = urlunparse((parsed.scheme, parsed.netloc, path, "", "limit=50&depth=2", ""))

        def _do():
            from curl_cffi import requests as cffi_requests

            response = cffi_requests.get(
                json_url,
                impersonate="firefox133",
                timeout=15,
                headers={"Accept": "application/json", "Accept-Language": "en-US,en;q=0.9"},
            )
            response.raise_for_status()
            return response.json()

        try:
            data = await loop.run_in_executor(None, _do)
        except Exception:
            return ""

        lines = []
        post_listing = data[0]["data"]["children"][0]["data"] if data else {}
        title = post_listing.get("title", "")
        selftext = post_listing.get("selftext", "")
        subreddit = post_listing.get("subreddit", "")
        author = post_listing.get("author", "")
        score = post_listing.get("score", 0)
        lines.append(f"r/{subreddit} | u/{author} | score: {score}")
        lines.append(f"# {title}")
        if selftext:
            lines.append(selftext)
        return "\n".join(lines)[: settings.search.lightweight_read_char_budget]

    async def _read_url(self, url: str) -> str:
        """Read lightweight text from supported URLs with site-specific fallbacks."""

        if self._is_skippable(url):
            return ""
        if self._is_youtube(url):
            return await asyncio.get_running_loop().run_in_executor(None, self._extract_youtube_transcript_sync, url)

        host = urlparse(url).netloc.lower().removeprefix("www.")
        if host in {"reddit.com", "old.reddit.com"} or host.endswith(".reddit.com"):
            return await self._fetch_reddit_json(url)

        client = await self._get_http_client()
        try:
            response = await client.get(url)
            response.raise_for_status()
            raw = response.text
        except Exception:
            try:
                from curl_cffi import requests as cffi_requests

                def _do():
                    result = cffi_requests.get(url, impersonate="chrome124", timeout=12)
                    result.raise_for_status()
                    return result.text

                raw = await asyncio.get_running_loop().run_in_executor(None, _do)
            except Exception:
                return ""

        raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"\s{2,}", "\n", re.sub(r"<[^>]+>", " ", raw)).strip()
        return unquote(text[: settings.search.lightweight_read_char_budget])

    async def _enrich_with_light_reads(self, results: list[SearchResult]) -> list[SearchResult]:
        """Attach lightweight page text to the top configured results."""

        if not settings.search.enable_lightweight_read:
            return results
        top_n = max(0, min(settings.search.lightweight_read_top_results, len(results)))
        if top_n == 0:
            return results

        targets = results[:top_n]
        payloads = await asyncio.gather(*[self._read_url(item.url) for item in targets], return_exceptions=True)
        for item, payload in zip(targets, payloads):
            if isinstance(payload, str) and payload.strip():
                item.page_text = payload.strip()
        return results


    # Public API
    async def search(
        self,
        query: str,
        limit: Optional[int] = None,
        language: Optional[str] = None,
        skip_cache: bool = False,
    ) -> list[SearchResult]:
        """Run cached multi-source search and enrich the top results."""

        limit = limit or settings.search_results_limit
        lang_code = language or settings.searxng_language
        lang = "ru" if "ru" in lang_code.lower() else "en"
        cache_key = self._cache_key(query, lang)

        # Reuse hot cache entries until they expire.
        if not skip_cache and cache_key in self._cache:
            entry = self._cache[cache_key]
            if entry.is_valid():
                return entry.results[:limit]
            del self._cache[cache_key]

        # Query both backends inside the shared concurrency budget.
        async with self._semaphore:
            yacy_task = asyncio.create_task(self._search_yacy(query, limit))
            ddgs_task = asyncio.create_task(self._search_ddgs(query, limit, lang))
            yacy_results, ddgs_results = await asyncio.gather(yacy_task, ddgs_task)

        # Normalize and enrich before storing the final shortlist.
        merged = self._merge_sources(yacy_results, ddgs_results, limit)
        deduped = self._sort_by_trust(self._deduplicate(merged))
        enriched = await self._enrich_with_light_reads(deduped[:limit])
        self._cache[cache_key] = CacheEntry(enriched, self.cache_ttl)
        return enriched[:limit]

    async def close(self):
        """Close the shared async HTTP client."""

        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    def format_for_agent(self, results: list[SearchResult], max_chars: int = 3500) -> str:
        """Format results into a compact text block for agent prompts."""

        if not results:
            return "No search results found."

        lines: list[str] = []
        total = 0
        for index, result in enumerate(results, 1):
            domain = result.domain.lower().replace("www.", "")
            trust = " [SOCIAL/UNTRUSTED]" if any(item in domain for item in self.UNTRUSTED_DOMAINS) else ""
            line = (
                f"{index}. [{result.title}]({result.url}) [{domain}] [{result.engine}]{trust}\n"
                f"   Snippet: {result.content}\n"
            )
            if result.page_text:
                excerpt = result.page_text[: settings.search.lightweight_read_char_budget]
                line += f"   Read: {excerpt}\n"
            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line)
        return "\n".join(lines)


search_client = SearchClient()
