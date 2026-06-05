# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from core.config import load_search_config
from core.extract.content_processor import compress_read_page_markdown
from core.extract.nextjs_rsc import extract_nextjs_rsc_text
from core.extract.page_normalizer import normalize_page
from core.fetch.antibot import is_antibot
from core.fetch.camoufox_fetcher import fetch_with_camoufox, is_camoufox_available
from core.fetch.url_utils import (
    UnsafeFetchUrl,
    has_non_text_extension,
    is_non_text_content_type,
    max_safe_redirects,
    validate_public_fetch_url,
    validate_redirect_target,
)
from core.registry.domain_registry import get_registry
from custom_domains.amazon import fetch_amazon_snapshot
from custom_domains.ebay import fetch_ebay_snapshot
from custom_domains.github import fetch_github_page as _fetch_github_page
from custom_domains.github import is_github_url as _is_github_url
from custom_domains.dns_shop import dns_variant_urls as _dns_variant_urls
from custom_domains.dns_shop import rewrite_read_page_url as _rewrite_read_page_url
from custom_domains.reddit import fetch_reddit_json as _fetch_reddit_json
from custom_domains.reddit import is_reddit as _is_reddit
from custom_domains.retail import extract_retail_metadata as _extract_retail_metadata
from custom_domains.retail import prepend_retail_metadata as _prepend_retail_metadata
from custom_domains.stackexchange import fetch_stackexchange_question
from custom_domains.stackexchange import is_stackexchange_question_url
from custom_domains.x import fetch_x_post as _fetch_x_post
from custom_domains.x import is_x_post as _is_x_post
from custom_domains.x import x_status_id as _x_status_id
from services.web_search import _cache

from core.fetch.constants import DEFAULT_UA as _UA
from core.fetch.thread_pool import io_pool as _io_pool

logger = logging.getLogger("services.read_page")
trace_logger = logging.getLogger("trace.read_page")
_READ_PAGE_STRATEGY_VERSION = "2026-04-followups-v1"


# True for HTTP redirect status codes.
def _is_redirect_status(status_code: int) -> bool:
    return status_code in {301, 302, 303, 307, 308}


_SKIP_HOSTS = ("twitter.com", "x.com", "vimeo.com", "tiktok.com")
_YT_HOSTS = ("youtube.com", "youtu.be", "www.youtube.com", "m.youtube.com")


# Extract normalized host from URL (no www/m prefix).
def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")


# True for YouTube watch/short URLs.
def _is_youtube(url: str) -> bool:
    return _host(url) in ("youtube.com", "youtu.be")


# True when read_page should not fetch HTML (non-text hosts/extensions).
def _is_skippable(url: str) -> bool:
    from core.extract.pdf_extractor import looks_like_pdf_url

    if looks_like_pdf_url(url):
        return False
    if has_non_text_extension(url):
        return True
    return any(_host(url) == s or _host(url).endswith("." + s) for s in _SKIP_HOSTS)


# Cache key including strategy tag and DNS variant label.
def _cache_key_for_read(url: str, *, strategy_tag: str, variant: str = "") -> str:
    parsed = urlparse(url)
    query_items = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "__rpv"]
    token = strategy_tag.strip() or _READ_PAGE_STRATEGY_VERSION
    suffix = f"{token}:{variant}" if variant else token
    query_items.append(("__rpv", suffix))
    query = urlencode(query_items, doseq=True)
    return urlunparse(parsed._replace(query=query))


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
    if not stripped:
        return True
    if len(stripped) < min_length:
        return True

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if len(lines) <= 4:
        return True

    boilerplate_hits = 0
    for marker in ("**Site:**", "**URL:**", "---"):
        if marker in stripped:
            boilerplate_hits += 1
    if boilerplate_hits >= 3 and len(lines) <= 6:
        return True

    return False


# Apply GLiNER/read_page compression budget from config.
def _apply_read_page_budget(
    markdown: str,
    *,
    url: str,
    focus: str,
    cfg,
    max_chars: int,
) -> str:
    ext = cfg.extraction
    return compress_read_page_markdown(
        markdown,
        url=url,
        focus=focus,
        max_chars=max_chars,
        compress_threshold=ext.read_page_compress_threshold_chars,
        compress_target=ext.read_page_compress_target_chars,
        enable_compress=ext.enable_read_page_compress,
        enable_gliner=cfg.search.enable_gliner,
    )


# Wrap already-extracted fallback text in minimal markdown headers.
def _fallback_text_to_markdown(url: str, text: str) -> str:
    host = _host(url)
    body = text.strip()
    return f"**Site:** {host}\n**URL:** {url}\n\n---\n\n{body}"


# Convert raw DOM innerText to minimal markdown (SPA last resort).
def _inner_text_to_markdown(url: str, inner_text: str) -> str:
    lines = [line for line in inner_text.splitlines() if line.strip()]
    return _fallback_text_to_markdown(url, "\n\n".join(lines))


# Extract Next.js RSC text and wrap as minimal markdown.
def _nextjs_rsc_to_markdown(url: str, raw_html: str) -> str:
    text = extract_nextjs_rsc_text(raw_html)
    if not text:
        return ""
    return _fallback_text_to_markdown(url, text)


# Parse 11-char YouTube video id from URL.
def _youtube_video_id(url: str) -> str | None:
    m = re.search(r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


# Fetch YouTube transcript: youtube-transcript-api, then yt-dlp fallback.
async def _fetch_youtube_transcript(url: str) -> str:
    video_id = _youtube_video_id(url)
    if not video_id:
        return f"Error: Could not extract video ID from: {url}"

    loop = asyncio.get_running_loop()

    # Attempt 1: youtube-transcript-api (no network overhead beyond one API call)
    # Returns: transcript text, "ERR:<message>" on known errors, or None to continue to yt-dlp
    def _yta_try() -> str | None:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except ImportError:
            return None

        PREFERRED = ["ru", "en", "uk", "de", "fr"]

        try:
            api = YouTubeTranscriptApi()
            if hasattr(api, "list"):
                transcript_list = api.list(video_id)
            else:
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        except Exception as e:
            err = str(e)
            if "unavailable" in err.lower() or "no longer available" in err.lower():
                return f"ERR:Video unavailable: {url}"
            logger.debug("youtube_transcript_api list() failed for %s: %s", url, e)
            # Any other list error вЂ” fall through to yt-dlp
            return None

        # Try manual transcripts in preferred order
        fetched = None
        for lang in PREFERRED:
            try:
                fetched = transcript_list.find_manually_created_transcript([lang])
                break
            except Exception:
                logger.debug("Manual transcript unavailable for %s lang=%s", url, lang)
                continue

        # Fall back to generated transcripts in preferred order
        if fetched is None:
            for lang in PREFERRED:
                try:
                    fetched = transcript_list.find_generated_transcript([lang])
                    break
                except Exception:
                    logger.debug("Generated transcript unavailable for %s lang=%s", url, lang)
                    continue

        # Fall back to any available transcript, translate to English if needed
        if fetched is None:
            try:
                fetched = next(iter(transcript_list))
                if fetched.language_code not in PREFERRED:
                    try:
                        fetched = fetched.translate("en")
                    except Exception:
                        logger.debug("Transcript translation failed for %s from %s", url, fetched.language_code)
                        pass  # use original language
            except StopIteration:
                logger.debug("No transcripts available via youtube_transcript_api for %s", url)
                return None

        try:
            data = fetched.fetch()
            parts = [
                e.get("text", "") if isinstance(e, dict) else getattr(e, "text", "")
                for e in data
            ]
            text = " ".join(p for p in parts if p)
            if text:
                lang_code = getattr(fetched, "language_code", "?")
                return f"YouTube transcript [{lang_code}]\nVideo: {url}\n\n{text}"
        except Exception:
            logger.debug("youtube_transcript_api fetch() failed for %s", url, exc_info=True)
        return None

    result = await loop.run_in_executor(_io_pool,_yta_try)
    if result and result.startswith("ERR:"):
        return f"Error: {result[4:]}"
    if result:
        return result

    # Attempt 2: yt-dlp (heavier, downloads subtitle files)
    def _yt_dlp_try() -> str | None:
        try:
            import yt_dlp, tempfile, os, glob as _glob

            class _Silent:
                def debug(self, msg: str) -> None: pass
                def info(self, msg: str) -> None: pass
                def warning(self, msg: str) -> None: pass
                def error(self, msg: str) -> None: pass

            with tempfile.TemporaryDirectory() as tmpdir:
                opts = {
                    "skip_download": True,
                    "writesubtitles": True,
                    "writeautomaticsub": True,
                    "subtitleslangs": ["ru", "en", "uk", "de", "fr", "all"],
                    "subtitlesformat": "vtt",
                    "outtmpl": os.path.join(tmpdir, "sub"),
                    "quiet": True,
                    "no_warnings": True,
                    "logger": _Silent(),
                }
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([url])
                except Exception:
                    logger.debug("yt-dlp subtitle download failed for %s", url, exc_info=True)
                    return None
                vtt_files = _glob.glob(os.path.join(tmpdir, "*.vtt"))
                if not vtt_files:
                    return None
                # Prefer ru/en subtitles; fall back to first available
                PREFERRED_LANGS = ["ru", "en", "uk", "de", "fr"]
                chosen = vtt_files[0]
                for lang in PREFERRED_LANGS:
                    candidates = [f for f in vtt_files if f".{lang}." in os.path.basename(f)]
                    if candidates:
                        chosen = candidates[0]
                        break
                raw = open(chosen, encoding="utf-8", errors="replace").read()
                lines, seen = [], set()
                for line in raw.splitlines():
                    line = line.strip()
                    if not line or line.startswith("WEBVTT") or "-->" in line or re.match(r"^\d+$", line):
                        continue
                    clean = re.sub(r"<[^>]+>", "", line).strip()
                    if clean and clean not in seen:
                        seen.add(clean)
                        lines.append(clean)
                text = " ".join(lines)
                return f"YouTube transcript (yt-dlp)\nVideo: {url}\n\n{text}" if text else None
        except Exception:
            logger.debug("yt-dlp transcript fallback crashed for %s", url, exc_info=True)
            return None

    result = await loop.run_in_executor(_io_pool,_yt_dlp_try)
    return result or f"Error: No transcript available for: {url}"


# Fetch HTML via httpx with per-redirect SSRF checks.
async def _fetch_httpx(url: str, timeout: float, tls_verify: bool = True) -> str | None:
    try:
        import httpx

        if not tls_verify:
            logger.warning("TLS verification disabled - MITM risk for %s", url)
        current_url = validate_public_fetch_url(url)
        async with httpx.AsyncClient(
            headers={"User-Agent": _UA, "Accept": "text/html,*/*;q=0.8"},
            timeout=timeout,
            follow_redirects=False,
            verify=tls_verify,
        ) as client:
            for _ in range(max_safe_redirects() + 1):
                r = await client.get(current_url)
                if _is_redirect_status(r.status_code):
                    current_url = validate_redirect_target(current_url, r.headers.get("location", ""))
                    continue
                break
            else:
                return None
            if 200 <= r.status_code < 400:
                if is_non_text_content_type(r.headers.get("content-type", "")):
                    return None
                text = r.text
                return text if text and not is_antibot(text) else None
    except UnsafeFetchUrl as exc:
        logger.warning("blocked unsafe read_page fetch url=%r reason=%s", url, exc)
    except Exception:
        logger.debug("httpx fetch failed for %s", url, exc_info=True)
    return None


# curl_cffi HTML fetch with the same redirect-by-redirect SSRF checks.
async def _fetch_curl_cffi(url: str, timeout: int) -> str | None:
    loop = asyncio.get_running_loop()

    def _sync() -> str | None:
        try:
            from curl_cffi import requests as cffi_req

            current_url = validate_public_fetch_url(url)
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
                return None
            r.raise_for_status()
            if is_non_text_content_type(r.headers.get("content-type", "")):
                return None
            text = r.text
            return text if text and not is_antibot(text) else None
        except UnsafeFetchUrl as exc:
            logger.warning("blocked unsafe read_page curl url=%r reason=%s", url, exc)
            return None
        except Exception:
            logger.debug("curl_cffi fetch failed for %s", url, exc_info=True)
            return None

    return await loop.run_in_executor(_io_pool, _sync)


# Fetch PDF bytes with SSRF checks and MAX_PDF_BYTES ceiling.
async def _fetch_pdf_bytes(url: str, timeout: float, tls_verify: bool = True) -> bytes:
    from core.extract.pdf_extractor import MAX_PDF_BYTES, looks_like_pdf_bytes

    try:
        import httpx

        current_url = validate_public_fetch_url(url)
        headers = {"User-Agent": _UA, "Accept": "application/pdf,*/*;q=0.8"}
        async with httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            follow_redirects=False,
            verify=tls_verify,
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
            if 200 <= r.status_code < 400 and len(data) <= MAX_PDF_BYTES and looks_like_pdf_bytes(data):
                return data
        except UnsafeFetchUrl as exc:
            logger.warning("blocked unsafe read_page PDF curl url=%r reason=%s", url, exc)
            return b""
        except Exception:
            logger.debug("curl_cffi PDF fetch failed for %s", url, exc_info=True)
            return b""
        return b""

    return await loop.run_in_executor(_io_pool, _sync)


# Download PDF and return markdown via pdf_bytes_to_markdown.
async def _read_pdf(url: str, timeout: float, tls_verify: bool, max_chars: int) -> str:
    from core.extract.pdf_extractor import pdf_bytes_to_markdown

    data = await _fetch_pdf_bytes(url, timeout=timeout, tls_verify=tls_verify)
    if not data:
        return f"Error: Could not fetch PDF content from: {url}"
    try:
        markdown = pdf_bytes_to_markdown(url=url, data=data, max_chars=max_chars)
    except Exception as exc:
        logger.warning("PDF extraction failed for %s: %s", url, exc)
        markdown = ""
    if not markdown:
        return f"Error: Could not extract text from PDF: {url}"
    _cache.cache_page(url, markdown.splitlines()[0].lstrip("# ").strip()[:500], markdown, "")
    return markdown


# Race httpx vs curl_cffi; first non-antibot response wins.
async def _fetch_race(url: str, timeout: float, tls_verify: bool = True) -> str | None:
    t_httpx = asyncio.create_task(_fetch_httpx(url, timeout, tls_verify=tls_verify))
    t_curl = asyncio.create_task(_fetch_curl_cffi(url, int(timeout) + 3))
    pending: set = {t_httpx, t_curl}
    result: str | None = None
    while pending and result is None:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            try:
                candidate = task.result()
                if candidate:
                    result = candidate
                    for p in pending:
                        p.cancel()
                    pending = set()
                    break
            except Exception:
                logger.debug("Fetch race task failed for %s", url, exc_info=True)
    return result


@dataclass
class ReadPageOptions:
    timeout: float = 20.0
    max_chars: int = 20_000
    focus: str = ""


@dataclass
class ReadPageVariantAttempt:
    url: str
    variant: str
    fetch_method: str
    markdown_length: int
    weak: bool
    winner: bool


# Fetch a single URL and return clean markdown text.
class ReadPageService:
    def __init__(self, options: Optional[ReadPageOptions] = None) -> None:
        cfg = load_search_config()
        self._cfg = cfg
        self._registry = get_registry()
        self._opts = options or ReadPageOptions(
            timeout=cfg.extraction.timeout_seconds,
            max_chars=cfg.extraction.max_page_chars,
        )
        self._focus = (self._opts.focus or "").strip()

    # Fetch raw HTML through Camoufox within read_page's deadline.
    async def _fetch_camoufox_raw_html(self, url: str, opts: ReadPageOptions) -> str | None:
        camoufox_kwargs: dict[str, object] = {
            "wait_sec": 4.0,
            "timeout_sec": min(float(opts.timeout), 20.0),
            "process_timeout": min(max(float(opts.timeout) + 5.0, 10.0), 25.0),
            "warmup_count": 0,
            "normalize": False,
        }
        camoufox_result = await fetch_with_camoufox(
            url,
            **camoufox_kwargs,
        )
        raw_html = camoufox_result.html if camoufox_result.success else None
        if not raw_html:
            detail = camoufox_result.error or "unknown browser fetch failure"
            logger.warning("Camoufox read_page fetch failed for %s: %s", url, detail)
            return None
        return raw_html

    # HTTP race or Camoufox depending on domain registry tier.
    async def _fetch_raw_html(self, url: str, opts: ReadPageOptions, original_url: str) -> str | None:
        if self._registry.needs_camoufox(url):
            return await self._fetch_camoufox_raw_html(url, opts)

        raw_html = await _fetch_race(url, timeout=opts.timeout, tls_verify=self._cfg.search.tls_verify)
        if not raw_html:
            raw_html = await self._fetch_camoufox_raw_html(url, opts)
        return raw_html

    # Return per-variant trace for debugging (no user-facing read).
    async def trace(self, url: str) -> list[ReadPageVariantAttempt]:
        _, attempts = await self._read(url.strip(), collect_attempts=True)
        return attempts

    # Like read() but also returns variant attempt trace.
    async def read_with_trace(self, url: str) -> tuple[str, list[ReadPageVariantAttempt]]:
        return await self._read(url.strip(), collect_attempts=True)

    # Core read pipeline: special hosts, variants, normalize, budget.
    async def _read(
        self,
        url: str,
        *,
        collect_attempts: bool,
    ) -> tuple[str, list[ReadPageVariantAttempt]]:
        from core.extract.pdf_extractor import looks_like_pdf_text_dump, looks_like_pdf_url

        opts = self._opts
        fetch_url = _rewrite_read_page_url(url)
        attempts: list[ReadPageVariantAttempt] = []

        logger.info("read_page url=%r fetch_url=%r", url, fetch_url)

        # SSRF and fast-path handlers (Stack Exchange, X, GitHub, etc.).
        try:
            validate_public_fetch_url(fetch_url)
        except UnsafeFetchUrl as exc:
            logger.warning("blocked unsafe read_page url=%r fetch_url=%r reason=%s", url, fetch_url, exc)
            return f"Error: URL blocked by SSRF protection: {url}", attempts

        if is_stackexchange_question_url(url):
            return await fetch_stackexchange_question(url, timeout=opts.timeout), attempts

        if _is_x_post(url):
            return await _fetch_x_post(url, opts.timeout), attempts

        if _is_github_url(url):
            markdown = await _fetch_github_page(url, timeout=opts.timeout)
            markdown = _apply_read_page_budget(
                markdown,
                url=url,
                focus=self._focus,
                cfg=self._cfg,
                max_chars=opts.max_chars,
            )
            attempt = ReadPageVariantAttempt(
                url=url,
                variant="github_api",
                fetch_method="github_api",
                markdown_length=len(markdown or ""),
                weak=markdown.lstrip().lower().startswith("error:"),
                winner=True,
            )
            if collect_attempts:
                attempts.append(attempt)
            return markdown, attempts

        if _is_skippable(url):
            if has_non_text_extension(url):
                from core.fetch.download_types import get_download_info
                info = get_download_info(url)
                if info:
                    ext, category = info
                    return (
                        f"This URL points to a downloadable file, not a web page.\n"
                        f"  URL      : {url}\n"
                        f"  Extension: {ext}\n"
                        f"  Category : {category}"
                    ), attempts
            return f"Error: URL type not supported for text extraction: {url}", attempts

        if _is_youtube(url):
            return await _fetch_youtube_transcript(url), attempts

        if _is_reddit(url):
            try:
                return await _fetch_reddit_json(url), attempts
            except Exception as exc:
                logger.warning("Reddit fetch failed for %s: %s", url, exc)

        if _host(url) == "amazon.com":
            try:
                snapshot = await fetch_amazon_snapshot(url, timeout=opts.timeout)
                markdown = str(snapshot.get("markdown") or "").strip()
                blocked_like = bool(snapshot.get("blocked_like"))
                useless_banner = "continue shopping" in markdown.lower()
                if markdown and not blocked_like and not useless_banner:
                    attempt = ReadPageVariantAttempt(
                        url=url,
                        variant="amazon_custom",
                        fetch_method=str(snapshot.get("engine") or "custom"),
                        markdown_length=len(markdown),
                        weak=False,
                        winner=True,
                    )
                    if collect_attempts:
                        attempts.append(attempt)
                    return markdown, attempts
            except Exception:
                logger.debug("Amazon custom snapshot failed for %s, falling through", url, exc_info=True)

        if _host(url) == "ebay.com":
            try:
                snapshot = await fetch_ebay_snapshot(url, timeout=opts.timeout)
                markdown = str(snapshot.get("markdown") or "").strip()
                if markdown:
                    attempt = ReadPageVariantAttempt(
                        url=url,
                        variant="ebay_custom",
                        fetch_method=str(snapshot.get("engine") or "custom"),
                        markdown_length=len(markdown),
                        weak=False,
                        winner=True,
                    )
                    if collect_attempts:
                        attempts.append(attempt)
                    return markdown, attempts
            except Exception:
                logger.debug("eBay custom snapshot failed for %s, falling through", url, exc_info=True)

        if looks_like_pdf_url(url):
            return await _read_pdf(
                url,
                timeout=opts.timeout,
                tls_verify=self._cfg.search.tls_verify,
                max_chars=opts.max_chars,
            ), attempts

        # DNS-shop and generic HTML fetch with cache + weak-extraction retries.
        fetch_candidates = _dns_variant_urls(url) if _host(url) == "dns-shop.ru" else [fetch_url]
        markdown = ""
        raw_html: str | None = None

        for idx, candidate_url in enumerate(fetch_candidates):
            variant_label = _variant_label(candidate_url)
            cache_key = _cache_key_for_read(
                candidate_url,
                strategy_tag=_READ_PAGE_STRATEGY_VERSION,
                variant=variant_label,
            )
            cached_page = _cache.get_cached(cache_key)
            fetch_method = "cache"
            if cached_page and _cache.is_fresh(cache_key) and cached_page.raw_html:
                candidate_html: str | None = cached_page.raw_html
            else:
                fetch_method = "network"
                candidate_html = await self._fetch_raw_html(candidate_url, opts, url)

            if not candidate_html:
                attempt = ReadPageVariantAttempt(
                    url=candidate_url,
                    variant=variant_label,
                    fetch_method=fetch_method,
                    markdown_length=0,
                    weak=True,
                    winner=False,
                )
                if collect_attempts:
                    attempts.append(attempt)
                trace_logger.info(
                    "read_page.variant url=%r variant=%s fetch=%s markdown_len=0 weak=True winner=False",
                    candidate_url,
                    variant_label,
                    fetch_method,
                )
                continue

            raw_html = candidate_html
            if is_antibot(raw_html):
                attempt = ReadPageVariantAttempt(
                    url=candidate_url,
                    variant=variant_label,
                    fetch_method=fetch_method,
                    markdown_length=0,
                    weak=True,
                    winner=False,
                )
                if collect_attempts:
                    attempts.append(attempt)
                continue

            if looks_like_pdf_text_dump(raw_html):
                return await _read_pdf(
                    url,
                    timeout=opts.timeout,
                    tls_verify=self._cfg.search.tls_verify,
                    max_chars=opts.max_chars,
                ), attempts

            retail_meta = _extract_retail_metadata(candidate_url, raw_html)
            candidate_markdown = ""
            if self._registry.prefers_nextjs_rsc(candidate_url):
                candidate_markdown = _nextjs_rsc_to_markdown(candidate_url, raw_html)
                if candidate_markdown:
                    candidate_markdown = _prepend_retail_metadata(candidate_markdown, retail_meta)
                    fetch_method = f"{fetch_method}_rsc"

            if not candidate_markdown:
                candidate_markdown = normalize_page(candidate_url, raw_html)
                candidate_markdown = _prepend_retail_metadata(candidate_markdown, retail_meta)
            markdown = candidate_markdown
            weak = _is_weak_extraction(candidate_markdown, min_length=self._cfg.extraction.min_content_length)
            if fetch_method == "network" and not weak and not is_antibot(raw_html):
                _cache.cache_page(cache_key, "", clean_text="", raw_html=raw_html)
            if _host(url) == "dns-shop.ru" and fetch_method == "cache" and weak:
                refreshed_html = await self._fetch_raw_html(candidate_url, opts, url)
                if refreshed_html and not is_antibot(refreshed_html):
                    _cache.cache_page(cache_key, "", clean_text="", raw_html=refreshed_html)
                    refreshed_meta = _extract_retail_metadata(candidate_url, refreshed_html)
                    refreshed_markdown = normalize_page(candidate_url, refreshed_html)
                    refreshed_markdown = _prepend_retail_metadata(refreshed_markdown, refreshed_meta)
                    refreshed_weak = _is_weak_extraction(
                        refreshed_markdown,
                        min_length=self._cfg.extraction.min_content_length,
                    )
                    if not refreshed_weak or len(refreshed_markdown or "") > len(candidate_markdown or ""):
                        raw_html = refreshed_html
                        candidate_markdown = refreshed_markdown
                        markdown = refreshed_markdown
                        weak = refreshed_weak
                        fetch_method = "network_refresh"
            if weak and fetch_method == "network" and not self._registry.needs_camoufox(candidate_url):
                if is_camoufox_available():
                    logger.info("weak extraction for %s - retrying via camoufox SPA fallback", candidate_url)
                    camoufox_result = await fetch_with_camoufox(
                        candidate_url,
                        wait_sec=4.0,
                        timeout_sec=opts.timeout,
                        process_timeout=opts.timeout + 15.0,
                        warmup_count=0,
                        normalize=False,
                    )
                    if camoufox_result.success and camoufox_result.html:
                        spa_markdown = normalize_page(candidate_url, camoufox_result.html)
                        spa_weak = _is_weak_extraction(
                            spa_markdown,
                            min_length=self._cfg.extraction.min_content_length,
                        )
                        if not spa_weak or len(spa_markdown) > len(candidate_markdown or ""):
                            raw_html = camoufox_result.html
                            candidate_markdown = spa_markdown
                            markdown = spa_markdown
                            weak = spa_weak
                            fetch_method = "camoufox"
                        elif (
                            spa_weak
                            and camoufox_result.inner_text
                            and len(camoufox_result.inner_text.strip()) > self._cfg.extraction.min_content_length
                        ):
                            inner_text_markdown = _inner_text_to_markdown(candidate_url, camoufox_result.inner_text)
                            inner_text_weak = _is_weak_extraction(
                                inner_text_markdown,
                                min_length=self._cfg.extraction.min_content_length,
                            )
                            if not inner_text_weak or len(inner_text_markdown) > len(candidate_markdown or ""):
                                raw_html = camoufox_result.html
                                candidate_markdown = inner_text_markdown
                                markdown = inner_text_markdown
                                weak = inner_text_weak
                                fetch_method = "camoufox_innertext"
                                logger.info("SPA innerText fallback used for %s", candidate_url)
                        if weak:
                            rsc_markdown = _nextjs_rsc_to_markdown(candidate_url, camoufox_result.html)
                            if rsc_markdown:
                                rsc_weak = _is_weak_extraction(
                                    rsc_markdown,
                                    min_length=self._cfg.extraction.min_content_length,
                                )
                                if not rsc_weak or len(rsc_markdown) > len(candidate_markdown or ""):
                                    raw_html = camoufox_result.html
                                    candidate_markdown = rsc_markdown
                                    markdown = rsc_markdown
                                    weak = rsc_weak
                                    fetch_method = "camoufox_rsc"
                                    logger.info("SPA Next.js RSC fallback used for %s", candidate_url)
            winner = _host(url) != "dns-shop.ru" or not weak or idx == len(fetch_candidates) - 1
            attempt = ReadPageVariantAttempt(
                url=candidate_url,
                variant=variant_label,
                fetch_method=fetch_method,
                markdown_length=len(candidate_markdown or ""),
                weak=weak,
                winner=winner,
            )
            if collect_attempts:
                attempts.append(attempt)
            trace_logger.info(
                "read_page.variant url=%r variant=%s fetch=%s markdown_len=%d weak=%s winner=%s",
                candidate_url,
                variant_label,
                fetch_method,
                len(candidate_markdown or ""),
                weak,
                winner,
            )

            if _host(url) != "dns-shop.ru":
                break
            if not weak:
                break
            logger.info("Weak DNS extraction for %s via %s; trying next variant", url, candidate_url)
            if idx == len(fetch_candidates) - 1:
                break

        if not raw_html:
            return f"Error: Could not fetch content from: {url}", attempts

        if is_antibot(raw_html):
            return (
                f"Error: Anti-bot protection detected on {url}. "
                "Cannot extract content without a browser."
            ), attempts

        if not markdown or len(markdown.strip()) < self._cfg.extraction.min_content_length:
            return f"Warning: Very little content extracted from: {url}\n\n{markdown}", attempts

        markdown = _apply_read_page_budget(
            markdown,
            url=url,
            focus=self._focus,
            cfg=self._cfg,
            max_chars=opts.max_chars,
        )

        return markdown, attempts

    # Public entry: fetch URL as markdown with global deadline.
    async def read(self, url: str) -> str:
        url = url.strip()
        deadline = max(float(self._opts.timeout), 30.0)
        try:
            markdown, _ = await asyncio.wait_for(
                self._read(url, collect_attempts=False),
                timeout=deadline,
            )
        except asyncio.TimeoutError:
            logger.warning("read_page global deadline exceeded (%.0fs) for %s", deadline, url)
            return f"Error: Page read timed out after {int(deadline)}s: {url}"
        return markdown


# Convenience entry point for MCP adapter and CLI.
async def run_read_page(
    url: str,
    timeout: float = 20.0,
    max_chars: int = 20_000,
    focus: str = "",
) -> str:
    opts = ReadPageOptions(
        timeout=timeout,
        max_chars=max_chars,
        focus=focus,
    )
    service = ReadPageService(options=opts)
    return await service.read(url)
