# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import random
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse, urlunparse

import httpx

from .config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Optional overdrive dependencies
# ---------------------------------------------------------------------------

try:
    from patchright.async_api import async_playwright as _patchright_playwright
    _PATCHRIGHT_AVAILABLE = True
except ImportError:
    _PATCHRIGHT_AVAILABLE = False
    logger.debug("Patchright not installed, overdrive will skip it")

try:
    import pytesseract
    from PIL import Image
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False
    logger.debug("OCR dependencies not installed, overdrive OCR will skip it")


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
            text = await self._fetch_reddit_json(url)
            if text.strip():
                return text
            # .json API blocked (403) — fall through to overdrive/httpx
            if settings.search.overdrive:
                return await self._read_url_overdrive(url)
            return ""

        # Overdrive mode: multi-method staggered race.
        if settings.search.overdrive:
            return await self._read_url_overdrive(url)

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


    # ------------------------------------------------------------------
    # Overdrive fetch methods
    # ------------------------------------------------------------------

    _browser_semaphore: asyncio.Semaphore | None = None

    @staticmethod
    def _html_to_text(raw_html: str) -> str:
        """Cheap tag-stripping to get readable text from HTML."""
        raw = re.sub(
            r"<(script|style)[^>]*>.*?</\1>", "", raw_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return re.sub(r"\s{2,}", "\n", re.sub(r"<[^>]+>", " ", raw)).strip()

    _BLOCK_MARKERS = (
        "access denied", "403 forbidden", "cloudflare",
        "just a moment", "checking your browser", "enable javascript",
    )

    @classmethod
    def _is_valid_text(cls, text: str) -> bool:
        """Return True when *text* looks like real page content."""
        stripped = text.strip()
        if len(stripped) <= 150:
            return False
        lowered = stripped[:2000].lower()
        return not any(m in lowered for m in cls._BLOCK_MARKERS)

    async def _fetch_httpx(self, url: str) -> str:
        """Overdrive method 1: plain httpx GET."""
        client = await self._get_http_client()
        resp = await client.get(url)
        resp.raise_for_status()
        return self._html_to_text(resp.text)

    async def _fetch_curl_cffi(self, url: str) -> str:
        """Overdrive method 2: curl_cffi with Chrome TLS fingerprint."""
        from curl_cffi import requests as cffi_requests
        loop = asyncio.get_running_loop()

        def _do():
            r = cffi_requests.get(
                url, impersonate="chrome124", timeout=15,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            r.raise_for_status()
            return r.text

        raw = await loop.run_in_executor(None, _do)
        return self._html_to_text(raw)

    async def _fetch_camoufox_overdrive(self, url: str) -> tuple[str, Optional[bytes]]:
        """Overdrive method 3: standalone Camoufox (Firefox).

        Returns ``(text, screenshot_bytes | None)``.
        """
        loop = asyncio.get_running_loop()
        human = settings.search.overdrive_human_behavior

        def _run_in_thread():
            import asyncio as _aio
            if sys.platform == "win32":
                _aio.set_event_loop_policy(_aio.WindowsProactorEventLoopPolicy())

            async def _do():
                from camoufox.async_api import AsyncCamoufox
                screenshot: bytes | None = None
                async with AsyncCamoufox(headless=True) as browser:
                    page = await browser.new_page()
                    try:
                        await page.goto(url, wait_until="networkidle", timeout=30_000)
                        if human:
                            await asyncio.sleep(random.uniform(0.5, 2.0))
                            scroll_px = random.randint(200, 600)
                            await page.mouse.move(random.randint(100, 400), random.randint(100, 300))
                            await page.mouse.move(random.randint(400, 800), random.randint(200, 500))
                            await page.evaluate(f"window.scrollBy(0, {scroll_px})")
                            await asyncio.sleep(random.uniform(0.3, 0.8))
                        text = await page.inner_text("body")
                        try:
                            screenshot = await page.screenshot(type="png")
                        except Exception:
                            pass
                        return text, screenshot
                    finally:
                        await page.close()

            return _aio.run(_do())

        return await loop.run_in_executor(None, _run_in_thread)

    async def _fetch_patchright(self, url: str) -> tuple[str, Optional[bytes]]:
        """Overdrive method 4: Patchright Chromium.

        Returns ``(text, screenshot_bytes | None)``.
        """
        if not _PATCHRIGHT_AVAILABLE:
            return "", None

        pw = await _patchright_playwright()
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=30_000)
                text = await page.evaluate("document.body.innerText")
                screenshot: bytes | None = None
                try:
                    screenshot = await page.screenshot(type="png")
                except Exception:
                    pass
                return text or "", screenshot
            finally:
                await page.close()
        finally:
            await browser.close()
            await pw.stop()

    async def _fetch_ocr_fallback(self, screenshot_bytes: bytes) -> str:
        """Overdrive method 5: Tesseract OCR on a browser screenshot."""
        if not _OCR_AVAILABLE or not screenshot_bytes:
            return ""
        loop = asyncio.get_running_loop()

        def _do_ocr():
            image = Image.open(io.BytesIO(screenshot_bytes))
            return pytesseract.image_to_string(image, lang="eng+rus")

        return await asyncio.wait_for(
            loop.run_in_executor(None, _do_ocr),
            timeout=settings.search.overdrive_ocr_timeout,
        )

    async def _read_url_overdrive(self, url: str) -> str:
        """Overdrive orchestrator: staggered race of multiple fetch methods."""

        cfg = settings.search
        char_budget = cfg.lightweight_read_char_budget

        # Lazy-init browser semaphore.
        if SearchClient._browser_semaphore is None:
            SearchClient._browser_semaphore = asyncio.Semaphore(cfg.overdrive_browser_concurrency)
        sem = SearchClient._browser_semaphore

        best_screenshot: bytes | None = None
        result_text: str | None = None
        done_event = asyncio.Event()

        async def _race_fast(coro, label: str):
            nonlocal result_text
            try:
                text = await coro
                if self._is_valid_text(text):
                    if result_text is None:
                        result_text = text
                        done_event.set()
                        logger.debug("overdrive: winner=%s", label)
            except Exception as exc:
                logger.debug("overdrive: %s failed: %s", label, exc)

        async def _race_browser(coro_fn, label: str):
            nonlocal result_text, best_screenshot
            async with sem:
                try:
                    text, screenshot = await coro_fn()
                    if screenshot and best_screenshot is None:
                        best_screenshot = screenshot
                    if self._is_valid_text(text):
                        if result_text is None:
                            result_text = text
                            done_event.set()
                            logger.debug("overdrive: winner=%s", label)
                except Exception as exc:
                    logger.debug("overdrive: %s failed: %s", label, exc)

        # Phase A — fast methods.
        fast_tasks = [
            asyncio.create_task(_race_fast(self._fetch_httpx(url), "httpx")),
            asyncio.create_task(_race_fast(self._fetch_curl_cffi(url), "curl_cffi")),
        ]

        try:
            await asyncio.wait_for(done_event.wait(), timeout=cfg.overdrive_browser_start_delay)
        except asyncio.TimeoutError:
            pass

        if result_text is not None:
            for t in fast_tasks:
                t.cancel()
            return unquote(result_text[:char_budget])

        # Phase B — browser methods.
        browser_tasks: list[asyncio.Task] = [
            asyncio.create_task(
                _race_browser(lambda: self._fetch_camoufox_overdrive(url), "camoufox")
            ),
        ]
        if _PATCHRIGHT_AVAILABLE:
            browser_tasks.append(
                asyncio.create_task(
                    _race_browser(lambda: self._fetch_patchright(url), "patchright")
                )
            )

        all_tasks = fast_tasks + browser_tasks

        try:
            await asyncio.wait_for(done_event.wait(), timeout=cfg.overdrive_parallel_timeout)
        except asyncio.TimeoutError:
            pass

        for t in all_tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*all_tasks, return_exceptions=True)

        if result_text is not None:
            return unquote(result_text[:char_budget])

        # Phase C — OCR fallback.
        if cfg.overdrive_ocr_fallback and _OCR_AVAILABLE and best_screenshot:
            try:
                ocr_text = await self._fetch_ocr_fallback(best_screenshot)
                if self._is_valid_text(ocr_text):
                    logger.debug("overdrive: winner=ocr")
                    return unquote(ocr_text[:char_budget])
            except Exception as exc:
                logger.debug("overdrive: OCR failed: %s", exc)

        logger.debug("overdrive: all methods failed for %s", url)
        return ""

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
        """Run cached web search and enrich the top results."""

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

        # Query the search backend inside the shared concurrency budget.
        async with self._semaphore:
            results = await self._search_ddgs(query, limit, lang)

        # Normalize and enrich before storing the final shortlist.
        deduped = self._sort_by_trust(self._deduplicate(results))
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
