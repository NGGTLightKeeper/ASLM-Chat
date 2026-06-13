# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import custom_domains
from custom_domains import FetchContext, GenericRequest, PageResult
from custom_domains.retail import extract_retail_metadata, prepend_retail_metadata

from core.cache import get_page_cache
from core.config import load_search_config
from core.extract.content_processor import compress_read_page_markdown
from core.extract.nextjs_rsc import extract_nextjs_rsc_text
from core.extract.page_normalizer import normalize_page
from core.fetch.antibot import is_antibot
from core.fetch.camoufox_fetcher import FetchResult, fetch_with_camoufox, is_camoufox_available
from core.fetch.constants import DEFAULT_UA as _UA
from core.fetch.download_types import get_download_info
from core.fetch.thread_pool import io_pool as _io_pool
from core.fetch.url_utils import (
    UnsafeFetchUrl,
    has_non_text_extension,
    is_non_text_content_type,
    max_safe_redirects,
    validate_public_fetch_url,
    validate_redirect_target,
)
from core.profiles import (
    METHOD_CAMOUFOX,
    METHOD_CURL_CFFI,
    METHOD_HTTPX,
    FetchAttempt,
    domain_of,
    get_override,
    get_runtime_profiles,
)

logger = logging.getLogger("services.read_page")
trace_logger = logging.getLogger("trace.read_page")

_READ_PAGE_STRATEGY_VERSION = "2026-06-core-v1"
_REDDIT_READ_TIMEOUT_SEC = 60.0
_SKIP_HOSTS = ("vimeo.com", "tiktok.com")


# Outcome of one low-level HTTP fetch with the metadata needed for runtime profiling.
@dataclass(slots=True)
class RawFetch:
    html: str | None
    method: str
    user_agent: str = ""
    status: int = 0
    fetch_ms: float = 0.0
    blocked: bool = False
    timed_out: bool = False

    # Build a FetchAttempt for the runtime profile store, folding in parse-time stats.
    def attempt(self, *, parse_ms: float = 0.0, quality: int = 0, success: bool = False) -> FetchAttempt:
        empty = not self.html
        return FetchAttempt(
            method=self.method,
            user_agent=self.user_agent,
            status=self.status,
            fetch_ms=self.fetch_ms,
            parse_ms=parse_ms,
            quality=quality,
            success=success,
            blocked=self.blocked,
            timed_out=self.timed_out,
            empty=empty or (quality == 0 and not success),
        )


# Extract normalized host from URL (no www/m prefix).
def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")


# True for HTTP redirect status codes.
def _is_redirect_status(status_code: int) -> bool:
    return status_code in {301, 302, 303, 307, 308}


# True when read_page should not fetch HTML (non-text hosts/extensions).
def _is_skippable(url: str) -> bool:
    from core.extract.pdf_extractor import looks_like_pdf_url

    if looks_like_pdf_url(url):
        return False
    if has_non_text_extension(url):
        return True
    return any(_host(url) == s or _host(url).endswith("." + s) for s in _SKIP_HOSTS)


# Cache key including strategy tag and variant label.
def _cache_key_for_read(url: str, *, variant: str = "") -> str:
    parsed = urlparse(url)
    query_items = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "__rpv"]
    suffix = f"{_READ_PAGE_STRATEGY_VERSION}:{variant}" if variant else _READ_PAGE_STRATEGY_VERSION
    query_items.append(("__rpv", suffix))
    return urlunparse(parsed._replace(query=urlencode(query_items, doseq=True)))


# Label DNS-shop variant URLs for cache/trace.
def _variant_label(url: str) -> str:
    if url.endswith("/.xaml"):
        return "dns_xaml"
    if "/product/characteristics/" in url:
        return "dns_characteristics"
    return "default"


# True when extracted markdown is too short or mostly boilerplate.
def _is_weak_extraction(markdown: str, *, min_length: int) -> bool:
    if not markdown:
        return True
    stripped = markdown.strip()
    if not stripped or len(stripped) < min_length:
        return True
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if len(lines) <= 4:
        return True
    boilerplate_hits = sum(1 for marker in ("**Site:**", "**URL:**", "---") if marker in stripped)
    if boilerplate_hits >= 3 and len(lines) <= 6:
        return True
    return False


# Wrap already-extracted fallback text in minimal markdown headers.
def _fallback_text_to_markdown(url: str, text: str) -> str:
    return f"**Site:** {_host(url)}\n**URL:** {url}\n\n---\n\n{text.strip()}"


# Convert raw DOM innerText to minimal markdown (SPA last resort).
def _inner_text_to_markdown(url: str, inner_text: str) -> str:
    lines = [line for line in inner_text.splitlines() if line.strip()]
    return _fallback_text_to_markdown(url, "\n\n".join(lines))


# Extract Next.js RSC text and wrap as minimal markdown.
def _nextjs_rsc_to_markdown(url: str, raw_html: str) -> str:
    text = extract_nextjs_rsc_text(raw_html)
    return _fallback_text_to_markdown(url, text) if text else ""


# Fetch HTML via httpx with per-redirect SSRF checks; returns an instrumented RawFetch.
async def _fetch_httpx(url: str, timeout: float, tls_verify: bool = True) -> RawFetch:
    t0 = time.perf_counter()
    try:
        import httpx

        current_url = validate_public_fetch_url(url)
        async with httpx.AsyncClient(
            headers={"User-Agent": _UA, "Accept": "text/html,*/*;q=0.8"},
            timeout=timeout,
            follow_redirects=False,
            verify=tls_verify,
        ) as client:
            r = None
            for _ in range(max_safe_redirects() + 1):
                r = await client.get(current_url)
                if _is_redirect_status(r.status_code):
                    current_url = validate_redirect_target(current_url, r.headers.get("location", ""))
                    continue
                break
            else:
                return RawFetch(None, METHOD_HTTPX, _UA, 0, (time.perf_counter() - t0) * 1000)
            fetch_ms = (time.perf_counter() - t0) * 1000
            if r is not None and 200 <= r.status_code < 400:
                if is_non_text_content_type(r.headers.get("content-type", "")):
                    return RawFetch(None, METHOD_HTTPX, _UA, r.status_code, fetch_ms)
                text = r.text
                blocked = bool(text) and is_antibot(text)
                html = text if text and not blocked else None
                return RawFetch(html, METHOD_HTTPX, _UA, r.status_code, fetch_ms, blocked=blocked)
            return RawFetch(None, METHOD_HTTPX, _UA, r.status_code if r else 0, fetch_ms)
    except UnsafeFetchUrl as exc:
        logger.warning("blocked unsafe read_page fetch url=%r reason=%s", url, exc)
    except Exception:
        logger.debug("httpx fetch failed for %s", url, exc_info=True)
    return RawFetch(None, METHOD_HTTPX, _UA, 0, (time.perf_counter() - t0) * 1000)


# curl_cffi HTML fetch with the same redirect-by-redirect SSRF checks.
async def _fetch_curl_cffi(url: str, timeout: int) -> RawFetch:
    loop = asyncio.get_running_loop()

    def _sync() -> RawFetch:
        t0 = time.perf_counter()
        try:
            from curl_cffi import requests as cffi_req

            current_url = validate_public_fetch_url(url)
            r = None
            for _ in range(max_safe_redirects() + 1):
                r = cffi_req.get(
                    current_url,
                    impersonate="chrome124",
                    timeout=timeout,
                    headers={"User-Agent": _UA},
                    allow_redirects=False,
                )
                if _is_redirect_status(int(r.status_code)):
                    current_url = validate_redirect_target(current_url, r.headers.get("location", ""))
                    continue
                break
            else:
                return RawFetch(None, METHOD_CURL_CFFI, _UA, 0, (time.perf_counter() - t0) * 1000)
            fetch_ms = (time.perf_counter() - t0) * 1000
            if is_non_text_content_type(r.headers.get("content-type", "")):
                return RawFetch(None, METHOD_CURL_CFFI, _UA, int(r.status_code), fetch_ms)
            text = r.text
            blocked = bool(text) and is_antibot(text)
            html = text if text and 200 <= int(r.status_code) < 400 and not blocked else None
            return RawFetch(html, METHOD_CURL_CFFI, _UA, int(r.status_code), fetch_ms, blocked=blocked)
        except UnsafeFetchUrl as exc:
            logger.warning("blocked unsafe read_page curl url=%r reason=%s", url, exc)
        except Exception:
            logger.debug("curl_cffi fetch failed for %s", url, exc_info=True)
        return RawFetch(None, METHOD_CURL_CFFI, _UA, 0, (time.perf_counter() - t0) * 1000)

    return await loop.run_in_executor(_io_pool, _sync)


# Race httpx vs curl_cffi; first non-antibot response wins, loser is cancelled.
async def _fetch_race(url: str, timeout: float, tls_verify: bool = True) -> RawFetch:
    t_httpx = asyncio.create_task(_fetch_httpx(url, timeout, tls_verify=tls_verify))
    t_curl = asyncio.create_task(_fetch_curl_cffi(url, int(timeout) + 3))
    pending: set = {t_httpx, t_curl}
    last: RawFetch | None = None
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            try:
                candidate = task.result()
            except Exception:
                logger.debug("Fetch race task failed for %s", url, exc_info=True)
                continue
            last = candidate
            if candidate.html:
                for p in pending:
                    p.cancel()
                return candidate
    return last or RawFetch(None, METHOD_HTTPX, _UA, 0, 0.0)


# Run Camoufox within read_page's deadline and adapt the result into a RawFetch.
async def _fetch_camoufox(url: str, timeout: float) -> tuple[RawFetch, FetchResult | None]:
    result = await fetch_with_camoufox(
        url,
        wait_sec=4.0,
        timeout_sec=min(float(timeout), 20.0),
        process_timeout=min(max(float(timeout) + 5.0, 10.0), 25.0),
        warmup_count=0,
        normalize=False,
    )
    if not result.success or not result.html:
        detail = result.error or "unknown browser fetch failure"
        logger.warning("Camoufox read_page fetch failed for %s: %s", url, detail)
        timed_out = "timeout" in detail.lower()
        return RawFetch(None, METHOD_CAMOUFOX, "camoufox", 0, result.duration_sec * 1000, timed_out=timed_out), None
    return RawFetch(
        result.html, METHOD_CAMOUFOX, "camoufox", 200, result.duration_sec * 1000
    ), result


# Fetch PDF bytes with SSRF checks and the MAX_PDF_BYTES ceiling (httpx, then curl_cffi).
async def _fetch_pdf_bytes(url: str, timeout: float, tls_verify: bool = True) -> bytes:
    from core.extract.pdf_extractor import MAX_PDF_BYTES, looks_like_pdf_bytes

    try:
        import httpx

        current_url = validate_public_fetch_url(url)
        headers = {"User-Agent": _UA, "Accept": "application/pdf,*/*;q=0.8"}
        async with httpx.AsyncClient(
            headers=headers, timeout=timeout, follow_redirects=False, verify=tls_verify
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
                    if content_length > MAX_PDF_BYTES:
                        return b""
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in r.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_PDF_BYTES:
                            return b""
                        chunks.append(chunk)
                    data = b"".join(chunks)
                    if 200 <= r.status_code < 400 and looks_like_pdf_bytes(data):
                        return data
                    return b""
    except UnsafeFetchUrl as exc:
        logger.warning("blocked unsafe read_page PDF url=%r reason=%s", url, exc)
    except Exception:
        logger.debug("httpx PDF fetch failed for %s", url, exc_info=True)

    loop = asyncio.get_running_loop()

    def _sync() -> bytes:
        try:
            from curl_cffi import requests as cffi_req

            current_url = validate_public_fetch_url(url)
            for _ in range(max_safe_redirects() + 1):
                r = cffi_req.get(
                    current_url,
                    impersonate="chrome124",
                    timeout=int(timeout) + 3,
                    headers={"User-Agent": _UA, "Accept": "application/pdf,*/*;q=0.8"},
                    allow_redirects=False,
                )
                if _is_redirect_status(int(r.status_code)):
                    current_url = validate_redirect_target(current_url, r.headers.get("location", ""))
                    continue
                break
            else:
                return b""
            data = bytes(r.content or b"")
            if 200 <= int(r.status_code) < 400 and len(data) <= MAX_PDF_BYTES and looks_like_pdf_bytes(data):
                return data
        except UnsafeFetchUrl as exc:
            logger.warning("blocked unsafe read_page PDF curl url=%r reason=%s", url, exc)
        except Exception:
            logger.debug("curl_cffi PDF fetch failed for %s", url, exc_info=True)
        return b""

    return await loop.run_in_executor(_io_pool, _sync)


@dataclass
class ReadPageOptions:
    timeout: float = 20.0
    max_chars: int = 20_000
    focus: str = ""
    # When False, the heavy Camoufox browser path is disabled entirely. web_search
    # sets this so the browser stays exclusive to the read_page tool: a wide search
    # must be cheap/HTTP-only and skip browser-only sources rather than pay 7-16s a page.
    allow_browser: bool = True


# Global asyncio deadline for one read; Reddit needs room for curl + Camoufox JSON.
def _read_page_deadline(url: str, opts: ReadPageOptions) -> float:
    base = float(opts.timeout)
    if _host(url) == "reddit.com" or _host(url).endswith(".reddit.com"):
        return max(base, _REDDIT_READ_TIMEOUT_SEC)
    return max(base, 30.0)


# Fetch a single URL and return clean markdown text via the custom-domain dispatch
# layer and a profile-driven generic pipeline.
class ReadPageService:
    def __init__(self, options: Optional[ReadPageOptions] = None) -> None:
        cfg = load_search_config()
        self._cfg = cfg
        self._cache = get_page_cache()
        self._profiles = get_runtime_profiles()
        self._opts = options or ReadPageOptions(
            timeout=cfg.extraction.timeout_seconds,
            max_chars=cfg.extraction.max_page_chars,
        )
        self._focus = (self._opts.focus or "").strip()

    # Whether the heavy browser (Camoufox) path may run. Disabled by web_search so the
    # browser stays exclusive to the read_page tool.
    def _browser_ok(self) -> bool:
        return self._opts.allow_browser and is_camoufox_available()

    # Apply the read_page compression/GLiNER budget from config.
    def _apply_budget(self, markdown: str, url: str) -> str:
        ext = self._cfg.extraction
        return compress_read_page_markdown(
            markdown,
            url=url,
            focus=self._focus,
            max_chars=self._opts.max_chars,
            compress_threshold=ext.read_page_compress_threshold_chars,
            compress_target=ext.read_page_compress_target_chars,
            enable_compress=ext.enable_read_page_compress,
            enable_gliner=self._cfg.search.enable_gliner,
        )

    # Build the FetchContext handed to custom-domain handlers.
    def _context(self) -> FetchContext:
        return FetchContext(
            timeout=self._opts.timeout,
            max_chars=self._opts.max_chars,
            focus=self._focus,
            cfg=self._cfg,
            cache=self._cache,
            generic_read=self._generic_read,
        )

    # Pick the fetch strategy for a domain from hard overrides then runtime profiles.
    def _resolve_strategy(self, url: str, req: GenericRequest) -> tuple[bool, str | None, bool]:
        domain = domain_of(url)
        override = get_override(domain)
        hint = self._profiles.best_method(domain)

        prefer_rsc = req.prefer_rsc or bool(override and override.parsing_mode == "nextjs_rsc")
        camoufox_first = req.camoufox_first or bool(override and override.required_method == METHOD_CAMOUFOX)
        http_method: str | None = None
        if hint and not hint.avoid and hint.confidence >= 0.5:
            if hint.method == METHOD_CAMOUFOX:
                camoufox_first = True
            elif hint.method in (METHOD_HTTPX, METHOD_CURL_CFFI):
                http_method = hint.method
        return camoufox_first, http_method, prefer_rsc

    # Fetch one candidate URL with the chosen method (camoufox / single http / race).
    async def _fetch_candidate(
        self, url: str, *, camoufox_first: bool, http_method: str | None
    ) -> tuple[RawFetch, FetchResult | None]:
        if camoufox_first and self._browser_ok():
            return await _fetch_camoufox(url, self._opts.timeout)
        if http_method == METHOD_HTTPX:
            return await _fetch_httpx(url, self._opts.timeout, tls_verify=self._cfg.search.tls_verify), None
        if http_method == METHOD_CURL_CFFI:
            return await _fetch_curl_cffi(url, int(self._opts.timeout) + 3), None
        return await _fetch_race(url, self._opts.timeout, tls_verify=self._cfg.search.tls_verify), None

    # Generic fetch+normalise pipeline shared by the default path and strategy handlers.
    # Records every attempt into the runtime profile store so later reads skip dead ends.
    async def _generic_read(self, req: GenericRequest) -> PageResult:
        url = req.url
        min_len = self._cfg.extraction.min_content_length
        camoufox_first, http_method, prefer_rsc = self._resolve_strategy(url, req)
        variants = req.url_variants or [url]

        markdown = ""
        raw_html: str | None = None
        winning_method = ""

        for idx, cand in enumerate(variants):
            variant_label = _variant_label(cand)
            cache_key = _cache_key_for_read(cand, variant=variant_label)
            cached = self._cache.get_cached(cache_key)

            raw: RawFetch | None = None
            cam: FetchResult | None = None
            if cached and self._cache.is_fresh(cache_key) and cached.raw_html:
                html: str | None = cached.raw_html
                method = "cache"
            else:
                raw, cam = await self._fetch_candidate(
                    cand, camoufox_first=camoufox_first, http_method=http_method
                )
                html = raw.html
                method = raw.method

            if not html:
                if raw is not None:
                    self._profiles.record(cand, raw.attempt(success=False))
                continue

            # Anti-bot wall — escalate to a real browser once if not already there.
            if is_antibot(html):
                if raw is not None:
                    self._profiles.record(cand, raw.attempt(success=False))
                if method != METHOD_CAMOUFOX and self._browser_ok():
                    raw, cam = await _fetch_camoufox(cand, self._opts.timeout)
                    if raw.html and not is_antibot(raw.html):
                        html, method = raw.html, METHOD_CAMOUFOX
                    else:
                        if raw is not None:
                            self._profiles.record(cand, raw.attempt(success=False))
                        continue
                else:
                    continue

            # A served PDF text dump should go through the PDF extractor instead.
            from core.extract.pdf_extractor import looks_like_pdf_text_dump

            if looks_like_pdf_text_dump(html):
                return await self._read_pdf(url)

            parse0 = time.perf_counter()
            retail_meta = extract_retail_metadata(cand, html)
            md = ""
            if prefer_rsc:
                md = _nextjs_rsc_to_markdown(cand, html)
                if md:
                    md = prepend_retail_metadata(md, retail_meta)
            if not md:
                md = prepend_retail_metadata(normalize_page(cand, html), retail_meta)
            parse_ms = (time.perf_counter() - parse0) * 1000
            weak = _is_weak_extraction(md, min_length=min_len)

            if raw is not None:
                self._profiles.record(
                    cand, raw.attempt(parse_ms=parse_ms, quality=len(md), success=not weak)
                )

            if method != "cache" and not weak and not is_antibot(html):
                self._cache.cache_page(cache_key, "", clean_text="", raw_html=html)

            # Weak HTML extraction — retry through Camoufox (normalize → innerText → RSC).
            if weak and method not in (METHOD_CAMOUFOX, "cache") and self._browser_ok():
                logger.info("weak extraction for %s — retrying via camoufox SPA fallback", cand)
                craw, cres = await _fetch_camoufox(cand, self._opts.timeout)
                if craw.html and cres is not None:
                    md, weak, method = self._spa_recover(cand, cres, md, min_len)
                    html = cres.html
                    self._profiles.record(cand, craw.attempt(quality=len(md), success=not weak))
                else:
                    self._profiles.record(cand, craw.attempt(success=False))

            raw_html, markdown, winning_method = html, md, method

            trace_logger.info(
                "read_page.variant url=%r variant=%s method=%s markdown_len=%d weak=%s",
                cand, variant_label, method, len(md), weak,
            )
            if not weak or idx == len(variants) - 1:
                break

        if not raw_html:
            return PageResult(markdown=f"Error: Could not fetch content from: {url}", ok=False)
        if is_antibot(raw_html):
            return PageResult(
                markdown=(
                    f"Error: Anti-bot protection detected on {url}. "
                    "Cannot extract content without a browser."
                ),
                ok=False,
                blocked=True,
            )
        if not markdown or len(markdown.strip()) < min_len:
            return PageResult(
                markdown=f"Warning: Very little content extracted from: {url}\n\n{markdown}",
                ok=True,
                method=winning_method,
            )
        return PageResult(markdown=markdown, ok=True, method=winning_method, apply_budget=True)

    # Recover the best markdown from a Camoufox SPA render: normalize → innerText → RSC.
    def _spa_recover(
        self, url: str, cres: FetchResult, prev_md: str, min_len: int
    ) -> tuple[str, bool, str]:
        spa_md = normalize_page(url, cres.html)
        spa_weak = _is_weak_extraction(spa_md, min_length=min_len)
        if not spa_weak or len(spa_md) > len(prev_md or ""):
            return spa_md, spa_weak, METHOD_CAMOUFOX

        if cres.inner_text and len(cres.inner_text.strip()) > min_len:
            it_md = _inner_text_to_markdown(url, cres.inner_text)
            if not _is_weak_extraction(it_md, min_length=min_len) or len(it_md) > len(prev_md or ""):
                logger.info("SPA innerText fallback used for %s", url)
                return it_md, _is_weak_extraction(it_md, min_length=min_len), "camoufox_innertext"

        rsc_md = _nextjs_rsc_to_markdown(url, cres.html)
        if rsc_md and (not _is_weak_extraction(rsc_md, min_length=min_len) or len(rsc_md) > len(prev_md or "")):
            logger.info("SPA Next.js RSC fallback used for %s", url)
            return rsc_md, _is_weak_extraction(rsc_md, min_length=min_len), "camoufox_rsc"

        return prev_md, True, METHOD_CAMOUFOX

    # Download a PDF and return extracted markdown.
    async def _read_pdf(self, url: str) -> PageResult:
        from core.extract.pdf_extractor import pdf_bytes_to_markdown

        data = await _fetch_pdf_bytes(url, timeout=self._opts.timeout, tls_verify=self._cfg.search.tls_verify)
        if not data:
            return PageResult(markdown=f"Error: Could not fetch PDF content from: {url}", ok=False)
        try:
            markdown = pdf_bytes_to_markdown(url=url, data=data, max_chars=self._opts.max_chars)
        except Exception as exc:
            logger.warning("PDF extraction failed for %s: %s", url, exc)
            markdown = ""
        if not markdown:
            return PageResult(markdown=f"Error: Could not extract text from PDF: {url}", ok=False)
        self._cache.cache_page(url, markdown.splitlines()[0].lstrip("# ").strip()[:500], markdown, "")
        return PageResult(markdown=markdown, ok=True, method="pdf")

    # Core read pipeline: SSRF, custom-domain dispatch, then the generic pipeline.
    async def _read(self, url: str) -> str:
        from core.extract.pdf_extractor import looks_like_pdf_url

        logger.info("read_page url=%r", url)
        try:
            validate_public_fetch_url(url)
        except UnsafeFetchUrl as exc:
            logger.warning("blocked unsafe read_page url=%r reason=%s", url, exc)
            return f"Error: URL blocked by SSRF protection: {url}"

        handler = custom_domains.match(url)
        if handler is not None:
            result = await handler.read(url, self._context())
            if result.ok or not getattr(handler, "fallback_to_generic", False):
                return self._finalize(url, result)

        if _is_skippable(url):
            if has_non_text_extension(url):
                info = get_download_info(url)
                if info:
                    ext, category = info
                    return (
                        f"This URL points to a downloadable file, not a web page.\n"
                        f"  URL      : {url}\n"
                        f"  Extension: {ext}\n"
                        f"  Category : {category}"
                    )
            return f"Error: URL type not supported for text extraction: {url}"

        if looks_like_pdf_url(url):
            result = await self._read_pdf(url)
            return self._finalize(url, result)

        result = await self._generic_read(GenericRequest(url=url))
        return self._finalize(url, result)

    # Apply the compression budget when the result asks for it, then return markdown.
    def _finalize(self, url: str, result: PageResult) -> str:
        markdown = result.markdown or ""
        if result.apply_budget and markdown and not markdown.lstrip().lower().startswith(("error:", "warning:")):
            markdown = self._apply_budget(markdown, url)
        return markdown

    # Public entry: fetch URL as markdown with a global deadline.
    async def read(self, url: str) -> str:
        url = url.strip()
        deadline = _read_page_deadline(url, self._opts)
        try:
            return await asyncio.wait_for(self._read(url), timeout=deadline)
        except asyncio.TimeoutError:
            logger.warning("read_page global deadline exceeded (%.0fs) for %s", deadline, url)
            return f"Error: Page read timed out after {int(deadline)}s: {url}"


# Convenience entry point for the central API and debug CLI.
async def run_read_page(
    url: str,
    timeout: float = 20.0,
    max_chars: int = 20_000,
    focus: str = "",
    allow_browser: bool = True,
) -> str:
    host = urlparse(url.strip()).netloc.lower().removeprefix("www.").removeprefix("m.")
    effective_timeout = max(timeout, _REDDIT_READ_TIMEOUT_SEC) if host == "reddit.com" else timeout
    service = ReadPageService(
        options=ReadPageOptions(
            timeout=effective_timeout, max_chars=max_chars, focus=focus, allow_browser=allow_browser
        )
    )
    return await service.read(url)
