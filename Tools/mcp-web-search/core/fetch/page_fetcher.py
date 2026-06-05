# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.cache.source_cache import CachedPage, SourceCache

logger = logging.getLogger("core.fetch.page_fetcher")


# True for HTTP redirect status codes we follow manually.
def _is_redirect_status(status_code: int) -> bool:
    return status_code in {301, 302, 303, 307, 308}


from core.fetch.antibot import is_antibot
from core.fetch.constants import DEFAULT_UA
from core.fetch.stackexchange_fetcher import fetch_stackexchange_question, is_stackexchange_question_url
from core.fetch.thread_pool import io_pool as _io_pool
from core.fetch.url_utils import (
    UnsafeFetchUrl,
    has_non_text_extension,
    is_non_text_content_type,
    max_safe_redirects,
    validate_public_fetch_url,
    validate_redirect_target,
)

_HEADERS = {
    "User-Agent": DEFAULT_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_SKIP_HOSTS = ("twitter.com", "x.com", "vimeo.com", "tiktok.com")

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


# Return True for URLs that cannot be usefully scraped as text.
def is_skippable(url: str) -> bool:
    from urllib.parse import urlparse
    from core.extract.pdf_extractor import looks_like_pdf_url

    if looks_like_pdf_url(url):
        return False

    if has_non_text_extension(url):
        return True
    host = urlparse(url).netloc.lower()
    return any(host == s or host.endswith("." + s) for s in _SKIP_HOSTS)


# Simple per-domain rate limiter using asyncio.
class _DomainThrottle:

    # min_interval derived from requests-per-second cap.
    def __init__(self, rps: float = 1.0) -> None:
        self._min_interval = 1.0 / max(rps, 0.01)
        self._last: dict[str, float] = defaultdict(float)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # Sleep until the domain is allowed another request.
    async def acquire(self, domain: str) -> None:
        async with self._locks[domain]:
            now = time.monotonic()
            elapsed = now - self._last[domain]
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last[domain] = time.monotonic()


# Async page fetcher: httpx → curl_cffi; stores results in SourceCache.
class PageFetcher:

    # Configure cache, concurrency, per-domain throttle, and TLS policy.
    def __init__(
        self,
        cache: SourceCache,
        max_concurrent: int = 6,
        per_domain_rps: float = 1.0,
        timeout: float = 10.0,
        store_raw_html: bool = False,
        tls_verify: bool = True,
    ) -> None:
        self._cache = cache
        self._sem = asyncio.Semaphore(max_concurrent)
        self._throttle = _DomainThrottle(per_domain_rps)
        self._timeout = timeout
        self._store_raw_html = store_raw_html
        self._tls_verify = tls_verify

    # httpx GET with per-redirect SSRF validation.
    async def _fetch_httpx(self, url: str) -> tuple[str, int]:
        import httpx

        current_url = validate_public_fetch_url(url)
        if not self._tls_verify:
            logger.warning("TLS verification disabled - MITM risk for %s", url)
        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=self._timeout,
            follow_redirects=False,
            verify=self._tls_verify,
        ) as client:
            for _ in range(max_safe_redirects() + 1):
                r = await client.get(current_url)
                if _is_redirect_status(r.status_code):
                    current_url = validate_redirect_target(current_url, r.headers.get("location", ""))
                    continue
                break
            else:
                return "", 0
            if is_non_text_content_type(r.headers.get("content-type", "")):
                return "", r.status_code
            return r.text, r.status_code

    # httpx streaming PDF download with redirect checks.
    async def _fetch_pdf_httpx(self, url: str, max_bytes: int) -> tuple[bytes, int]:
        import httpx

        current_url = validate_public_fetch_url(url)
        headers = dict(_HEADERS)
        headers["Accept"] = "application/pdf,*/*;q=0.8"
        async with httpx.AsyncClient(
            headers=headers,
            timeout=self._timeout,
            follow_redirects=False,
            verify=self._tls_verify,
        ) as client:
            for _ in range(max_safe_redirects() + 1):
                async with client.stream("GET", current_url) as r:
                    if _is_redirect_status(r.status_code):
                        current_url = validate_redirect_target(current_url, r.headers.get("location", ""))
                        continue
                    try:
                        content_length = int(r.headers.get("content-length", "0") or "0")
                    except ValueError:
                        content_length = 0
                    if content_length > max_bytes:
                        return b"", r.status_code
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in r.aiter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            return b"", r.status_code
                        chunks.append(chunk)
                    return b"".join(chunks), r.status_code
            return b"", 0

    # curl_cffi fallback with SSRF checks on each redirect.
    async def _fetch_curl_cffi(self, url: str) -> tuple[str, int]:
        loop = asyncio.get_running_loop()

        # Sync curl_cffi GET in the shared I/O pool.
        def _sync() -> tuple[str, int]:
            from curl_cffi import requests as cffi_req

            current_url = validate_public_fetch_url(url)
            for _ in range(max_safe_redirects() + 1):
                r = cffi_req.get(
                    current_url,
                    impersonate="chrome124",
                    timeout=self._timeout,
                    headers=_HEADERS,
                    allow_redirects=False,
                )
                if _is_redirect_status(int(r.status_code)):
                    current_url = validate_redirect_target(current_url, r.headers.get("location", ""))
                    continue
                break
            else:
                return "", 0
            if is_non_text_content_type(r.headers.get("content-type", "")):
                return "", r.status_code
            return r.text, r.status_code

        return await loop.run_in_executor(_io_pool, _sync)

    # curl_cffi PDF fallback with redirect checks.
    async def _fetch_pdf_curl_cffi(self, url: str, max_bytes: int) -> tuple[bytes, int]:
        loop = asyncio.get_running_loop()

        # Sync curl_cffi PDF GET in the shared I/O pool.
        def _sync() -> tuple[bytes, int]:
            from curl_cffi import requests as cffi_req

            current_url = validate_public_fetch_url(url)
            headers = dict(_HEADERS)
            headers["Accept"] = "application/pdf,*/*;q=0.8"
            for _ in range(max_safe_redirects() + 1):
                r = cffi_req.get(
                    current_url,
                    impersonate="chrome124",
                    timeout=self._timeout,
                    headers=headers,
                    allow_redirects=False,
                )
                if _is_redirect_status(int(r.status_code)):
                    current_url = validate_redirect_target(current_url, r.headers.get("location", ""))
                    continue
                break
            else:
                return b"", 0
            data = bytes(r.content or b"")
            if len(data) > max_bytes:
                return b"", r.status_code
            return data, r.status_code

        return await loop.run_in_executor(_io_pool, _sync)

    # Try httpx, then curl_cffi; returns (raw_html, status_code).
    async def _fetch_single(self, url: str) -> tuple[str, int]:
        from urllib.parse import urlparse
        try:
            validate_public_fetch_url(url)
        except UnsafeFetchUrl as exc:
            logger.warning("blocked unsafe page_fetcher url=%r reason=%s", url, exc)
            return "", 0
        domain = urlparse(url).netloc.lower()
        await self._throttle.acquire(domain)

        # Stage 1: httpx
        try:
            html, status = await asyncio.wait_for(
                self._fetch_httpx(url), timeout=self._timeout
            )
            if 200 <= status < 400 and html and len(html) > 100:
                return html, status
        except Exception as exc:
            logger.debug("httpx failed for %s: %s", url, exc)

        # Stage 2: curl_cffi
        try:
            html, status = await asyncio.wait_for(
                self._fetch_curl_cffi(url), timeout=self._timeout
            )
            if 200 <= status < 400 and html and len(html) > 100:
                return html, status
        except Exception as exc:
            logger.debug("curl_cffi failed for %s: %s", url, exc)

        return "", 0

    # Fetch PDF bytes bounded by MAX_PDF_BYTES.
    async def _fetch_pdf_bytes(self, url: str) -> bytes:
        from core.extract.pdf_extractor import MAX_PDF_BYTES, looks_like_pdf_bytes

        try:
            data, status = await asyncio.wait_for(
                self._fetch_pdf_httpx(url, MAX_PDF_BYTES),
                timeout=self._timeout,
            )
            if 200 <= status < 400 and data and looks_like_pdf_bytes(data):
                return data
        except Exception as exc:
            logger.debug("httpx PDF fetch failed for %s: %s", url, exc)

        try:
            data, status = await asyncio.wait_for(
                self._fetch_pdf_curl_cffi(url, MAX_PDF_BYTES),
                timeout=self._timeout,
            )
            if 200 <= status < 400 and data and looks_like_pdf_bytes(data):
                return data
        except Exception as exc:
            logger.debug("curl_cffi PDF fetch failed for %s: %s", url, exc)

        return b""

    # Download PDF, extract markdown, cache.
    async def _fetch_pdf_normalize_cache(self, url: str) -> CachedPage | None:
        from core.extract.pdf_extractor import pdf_bytes_to_markdown

        data = await self._fetch_pdf_bytes(url)
        if not data:
            self._cache.cache_page(url, "", "", "", status="error")
            return None

        try:
            clean_text = pdf_bytes_to_markdown(url=url, data=data)
        except Exception as exc:
            logger.info("PDF extraction failed for %s: %s", url, exc)
            clean_text = ""

        if not clean_text or len(clean_text) < 120:
            self._cache.cache_page(url, "", clean_text or "", "", status="error")
            return None

        title = clean_text.splitlines()[0].lstrip("# ").strip()[:500]
        self._cache.cache_page(url, title, clean_text, "", status="ok")
        return self._cache.get_cached(url)

    # Fetch one URL, normalize, and store in cache.
    async def _fetch_normalize_cache(self, url: str) -> CachedPage | None:
        async with self._sem:
            from core.extract.pdf_extractor import looks_like_decoded_binary, looks_like_pdf_text_dump, looks_like_pdf_url

            if looks_like_pdf_url(url):
                return await self._fetch_pdf_normalize_cache(url)

            if is_stackexchange_question_url(url):
                try:
                    clean_text = await fetch_stackexchange_question(url, timeout=self._timeout)
                except Exception as exc:
                    logger.warning("stackexchange fetch failed for %s: %s", url, exc)
                    self._cache.cache_page(url, "", "", "", status="error")
                    return None
                if clean_text.startswith("Error:"):
                    self._cache.cache_page(url, "", clean_text, "", status="error")
                    return None
                title = clean_text.splitlines()[0].lstrip("# ").strip()[:500]
                self._cache.cache_page(url, title, clean_text, "", status="ok")
                return self._cache.get_cached(url)

            try:
                raw_html, _status_code = await self._fetch_single(url)
            except Exception as exc:
                logger.warning("fetch failed for %s: %s", url, exc)
                self._cache.cache_page(url, "", "", "", status="error")
                return None

            if not raw_html:
                self._cache.cache_page(url, "", "", "", status="error")
                return None

            if looks_like_pdf_text_dump(raw_html):
                return await self._fetch_pdf_normalize_cache(url)

            if looks_like_decoded_binary(raw_html):
                logger.info("binary/text-garbage payload skipped for %s", url)
                self._cache.cache_page(url, "", "", "", status="error")
                return None

            if is_antibot(raw_html):
                self._cache.cache_page(url, "", "", status="antibot")
                return None

            # Normalize HTML to clean markdown.
            from core.extract.page_normalizer import normalize_page
            clean_text = normalize_page(url, raw_html, "")

            # Extract title from HTML.
            title = ""
            import html as html_lib
            m = _TITLE_RE.search(raw_html)
            if m:
                title = html_lib.unescape(m.group(1)).strip()[:500]

            stored_html = raw_html if self._store_raw_html else ""

            if not clean_text or len(clean_text) < 50:
                self._cache.cache_page(url, title, clean_text or "", stored_html, status="error")
                return None

            self._cache.cache_page(url, title, clean_text, stored_html, status="ok")
            return self._cache.get_cached(url)

    # Fetch up to budget URLs; skip URLs already fresh in cache.
    async def fetch_and_cache(
        self,
        urls: list[str],
        budget: int = 10,
    ) -> dict[str, CachedPage | None]:
        results: dict[str, CachedPage | None] = {}
        to_fetch: list[str] = []

        for u in urls:
            try:
                validate_public_fetch_url(u)
            except UnsafeFetchUrl as exc:
                logger.warning("blocked unsafe fetch_and_cache url=%r reason=%s", u, exc)
                results[u] = None
                continue
            if is_skippable(u):
                results[u] = None
            elif self._cache.is_fresh(u):
                results[u] = self._cache.get_cached(u)
            else:
                to_fetch.append(u)

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
