# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Lightweight page fetcher: httpx -> curl_cffi -> give up.

No browsers, no overdrive.  Designed for cache-first retrieval where
the goal is cheap, fast page downloads with strict budgets.

Public API
----------
PageFetcher          -- async fetcher that stores results in SourceCache
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from .source_cache import CachedPage, SourceCache

logger = logging.getLogger("page_fetcher")

# ---------------------------------------------------------------------------
# Anti-bot detection (inlined from engine.py to avoid heavy imports).
# ---------------------------------------------------------------------------
_ANTIBOT_MARKERS = (
    "antibot", "challenge", "captcha", "cf-browser-verification",
    "ray id", "just a moment", "checking your browser", "please wait",
    "enable javascript", "ddos-guard", "robot or human",
)
_ANTIBOT_SINGLE = (
    "your browser does not support javascript",
    "javascript is required",
    "please enable javascript",
    "this site requires javascript",
    "you need to enable javascript",
)


def _is_antibot(text: str) -> bool:
    t = text[:2000].lower()
    if any(m in t for m in _ANTIBOT_SINGLE):
        return True
    return sum(1 for m in _ANTIBOT_MARKERS if m in t) >= 2


# ---------------------------------------------------------------------------
# Default headers.
# ---------------------------------------------------------------------------
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ---------------------------------------------------------------------------
# Per-domain async rate limiter.
# ---------------------------------------------------------------------------
class _DomainThrottle:
    """Simple per-domain rate limiter using asyncio."""

    def __init__(self, rps: float = 1.0):
        self._min_interval = 1.0 / max(rps, 0.01)
        self._last: dict[str, float] = defaultdict(float)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def acquire(self, domain: str) -> None:
        async with self._locks[domain]:
            now = time.monotonic()
            elapsed = now - self._last[domain]
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last[domain] = time.monotonic()


# ---------------------------------------------------------------------------
# PageFetcher.
# ---------------------------------------------------------------------------
class PageFetcher:
    """Async page fetcher: httpx -> curl_cffi -> give up.

    Stores successful fetches in a SourceCache instance.
    """

    def __init__(
        self,
        cache: SourceCache,
        max_concurrent: int = 6,
        per_domain_rps: float = 1.0,
        timeout: float = 10.0,
        store_raw_html: bool = False,
    ):
        self._cache = cache
        self._sem = asyncio.Semaphore(max_concurrent)
        self._throttle = _DomainThrottle(per_domain_rps)
        self._timeout = timeout
        self._store_raw_html = store_raw_html

    # -- single URL fetch ----------------------------------------------------

    async def _fetch_httpx(self, url: str) -> tuple[str, int]:
        """Try fetching with httpx. Returns (raw_html, status_code)."""
        import httpx

        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=self._timeout,
            follow_redirects=True,
            verify=False,
        ) as client:
            r = await client.get(url)
            return r.text, r.status_code

    async def _fetch_curl_cffi(self, url: str) -> tuple[str, int]:
        """Fallback: curl_cffi with Chrome TLS fingerprint."""
        loop = asyncio.get_running_loop()

        def _sync():
            from curl_cffi import requests as cffi_req
            r = cffi_req.get(
                url,
                impersonate="chrome124",
                timeout=self._timeout,
                headers=_HEADERS,
            )
            return r.text, r.status_code

        return await loop.run_in_executor(None, _sync)

    async def _fetch_single(self, url: str) -> tuple[str, int]:
        """Try httpx, then curl_cffi. Returns (raw_html, status_code)."""
        domain = urlparse(url).netloc.lower()
        await self._throttle.acquire(domain)

        # Stage 1: httpx
        try:
            html, status = await asyncio.wait_for(
                self._fetch_httpx(url), timeout=self._timeout
            )
            if 200 <= status < 400 and html and len(html) > 100:
                return html, status
        except Exception as e:
            logger.debug("httpx failed for %s: %s", url, e)

        # Stage 2: curl_cffi
        try:
            html, status = await asyncio.wait_for(
                self._fetch_curl_cffi(url), timeout=self._timeout
            )
            if 200 <= status < 400 and html and len(html) > 100:
                return html, status
        except Exception as e:
            logger.debug("curl_cffi failed for %s: %s", url, e)

        return "", 0

    # -- normalize + store ---------------------------------------------------

    async def _fetch_normalize_cache(self, url: str) -> CachedPage | None:
        """Fetch a single URL, normalize, and store in cache."""
        async with self._sem:
            try:
                raw_html, status_code = await self._fetch_single(url)
            except Exception as e:
                logger.warning("fetch failed for %s: %s", url, e)
                self._cache.cache_page(url, "", "", "", status="error")
                return None

            if not raw_html:
                self._cache.cache_page(url, "", "", "", status="error")
                return None

            # Anti-bot check.
            if _is_antibot(raw_html):
                self._cache.cache_page(url, "", "", status="antibot")
                return None

            # Normalize HTML to clean markdown.
            try:
                from .page_normalizer import normalize_page
            except ImportError:
                from page_normalizer import normalize_page

            clean_text = normalize_page(url, raw_html, "")

            # Extract title from HTML.
            title = ""
            try:
                import re
                m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
                if m:
                    import html as html_lib
                    title = html_lib.unescape(m.group(1)).strip()[:500]
            except Exception:
                pass

            stored_html = raw_html if self._store_raw_html else ""

            if not clean_text or len(clean_text) < 50:
                self._cache.cache_page(url, title, clean_text or "", stored_html, status="error")
                return None

            self._cache.cache_page(url, title, clean_text, stored_html, status="ok")
            return self._cache.get_cached(url)

    # -- public API ----------------------------------------------------------

    async def fetch_and_cache(
        self,
        urls: list[str],
        budget: int = 10,
    ) -> dict[str, CachedPage | None]:
        """Fetch up to `budget` URLs, cache them, return url->CachedPage map.

        Skips URLs that are already fresh in the cache.
        """
        results: dict[str, CachedPage | None] = {}
        to_fetch: list[str] = []

        for u in urls:
            if self._cache.is_fresh(u):
                results[u] = self._cache.get_cached(u)
            else:
                to_fetch.append(u)

        # Enforce budget.
        to_fetch = to_fetch[:budget]

        if to_fetch:
            tasks = [self._fetch_normalize_cache(u) for u in to_fetch]
            fetched = await asyncio.gather(*tasks, return_exceptions=True)
            for u, result in zip(to_fetch, fetched):
                if isinstance(result, Exception):
                    logger.warning("fetch_and_cache error for %s: %s", u, result)
                    results[u] = None
                else:
                    results[u] = result

        return results

    async def ensure_cached(
        self,
        urls: list[str],
        ttl: int | None = None,
    ) -> dict[str, CachedPage | None]:
        """Return cached pages, fetching only those missing or stale."""
        results: dict[str, CachedPage | None] = {}
        to_fetch: list[str] = []

        for u in urls:
            if self._cache.is_fresh(u, max_age_sec=ttl):
                results[u] = self._cache.get_cached(u)
            else:
                to_fetch.append(u)

        if to_fetch:
            fetched = await self.fetch_and_cache(to_fetch, budget=len(to_fetch))
            results.update(fetched)

        return results
