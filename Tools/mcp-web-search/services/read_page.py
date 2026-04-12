# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Read Page service.

Fetch a single URL as clean markdown text. Supports:
  - Standard HTTP fetch (httpx → curl_cffi)
  - Reddit JSON endpoint
  - YouTube transcript (yt-dlp → youtube-transcript-api)
  - Wayback Machine fallback
  - page_normalizer for HTML → markdown conversion

Replaces the scattered read_page logic from legacy src/engine.py.

Public API
----------
ReadPageService         -- async service class
run_read_page(url, ...) -- top-level convenience coroutine
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urlunparse

from core.config import load_search_config
from core.extract.page_normalizer import normalize_page
from core.fetch.antibot import is_antibot
from core.fetch.url_utils import has_non_text_extension, is_non_text_content_type
from services.web_search import _cache

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

logger = logging.getLogger("services.read_page")


# ---------------------------------------------------------------------------
# URL classification helpers
# ---------------------------------------------------------------------------

_SKIP_HOSTS = ("twitter.com", "x.com", "vimeo.com", "tiktok.com")
_YT_HOSTS = ("youtube.com", "youtu.be", "www.youtube.com", "m.youtube.com")
_REDDIT_PATTERN = re.compile(r"reddit\.com/r/[^/]+/comments/")




def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")


def _is_youtube(url: str) -> bool:
    return _host(url) in ("youtube.com", "youtu.be")


def _is_reddit(url: str) -> bool:
    return bool(_REDDIT_PATTERN.search(url))


def _is_skippable(url: str) -> bool:
    from core.extract.pdf_extractor import looks_like_pdf_url

    if looks_like_pdf_url(url):
        return False
    if has_non_text_extension(url):
        return True
    return any(_host(url) == s or _host(url).endswith("." + s) for s in _SKIP_HOSTS)


def _is_downloadable(url: str) -> bool:
    return has_non_text_extension(url)


# ---------------------------------------------------------------------------
# YouTube transcript
# ---------------------------------------------------------------------------

def _youtube_video_id(url: str) -> str | None:
    m = re.search(r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


async def _fetch_youtube_transcript(url: str) -> str:
    """Fetch YouTube transcript: youtube-transcript-api → yt-dlp fallback."""
    video_id = _youtube_video_id(url)
    if not video_id:
        return f"Error: Could not extract video ID from: {url}"

    loop = asyncio.get_running_loop()

    # Attempt 1: youtube-transcript-api (no network overhead beyond one API call)
    def _yta_try() -> str | None:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            api = YouTubeTranscriptApi()
            for lang in ["ru", "en", "uk", "de", "fr"]:
                try:
                    transcript = api.fetch(video_id, languages=[lang])
                    parts = [
                        e.get("text", "") if isinstance(e, dict) else getattr(e, "text", "")
                        for e in transcript
                    ]
                    text = " ".join(p for p in parts if p)
                    if text:
                        return f"YouTube transcript\nVideo: {url}\n\n{text}"
                except Exception:
                    continue
        except Exception:
            pass
        return None

    result = await loop.run_in_executor(None, _yta_try)
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
                    "subtitleslangs": ["ru", "en"],
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
                    return None
                vtt_files = _glob.glob(os.path.join(tmpdir, "*.vtt"))
                if not vtt_files:
                    return None
                raw = open(vtt_files[0], encoding="utf-8", errors="replace").read()
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
            return None

    result = await loop.run_in_executor(None, _yt_dlp_try)
    return result or f"Error: No transcript available for: {url}"


# ---------------------------------------------------------------------------
# Reddit JSON fetch
# ---------------------------------------------------------------------------

async def _fetch_reddit_json(url: str) -> str:
    """Fetch Reddit post+comments via .json endpoint using Firefox TLS fingerprint."""
    import json as _json

    loop = asyncio.get_running_loop()
    p = urlparse(url)
    path = p.path.rstrip("/")
    if not path.endswith(".json"):
        path += ".json"
    json_url = urlunparse((p.scheme, p.netloc, path, "", "limit=50&depth=3", ""))

    def _do() -> dict:
        from curl_cffi import requests as _r
        resp = _r.get(json_url, impersonate="firefox133", timeout=15, headers={
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        })
        resp.raise_for_status()
        return resp.json()

    try:
        data = await loop.run_in_executor(None, _do)
    except Exception as exc:
        return f"Error: Reddit fetch failed: {exc}"

    lines: list[str] = []
    try:
        post = data[0]["data"]["children"][0]["data"]
    except (IndexError, KeyError, TypeError):
        return f"Error: Unexpected Reddit response structure for {url}"
    lines.append(f"r/{post.get('subreddit','')} | u/{post.get('author','')} | score: {post.get('score',0)}")
    lines.append(f"# {post.get('title','')}")
    if post.get("selftext"):
        lines.append(post["selftext"])
    lines.append("")

    def _comments(children: list, depth: int = 0) -> None:
        for child in children:
            if child.get("kind") != "t1":
                continue
            d = child["data"]
            body = d.get("body", "").strip()
            if body and body != "[deleted]":
                lines.append("  " * depth + f"[{d.get('author','?')} | +{d.get('score',0)}] {body}")
            replies = d.get("replies")
            if isinstance(replies, dict):
                _comments(replies["data"]["children"], depth + 1)

    if len(data) > 1:
        _comments(data[1]["data"]["children"])

    return "\n".join(lines)[:15_000]


# ---------------------------------------------------------------------------
# Standard HTTP fetch
# ---------------------------------------------------------------------------

async def _fetch_httpx(url: str, timeout: float, tls_verify: bool = True) -> str | None:
    try:
        import httpx
        if not tls_verify:
            logger.warning("TLS verification disabled — MITM risk for %s", url)
        async with httpx.AsyncClient(
            headers={"User-Agent": _UA, "Accept": "text/html,*/*;q=0.8"},
            timeout=timeout, follow_redirects=True, verify=tls_verify,
        ) as client:
            r = await client.get(url)
            if 200 <= r.status_code < 400:
                if is_non_text_content_type(r.headers.get("content-type", "")):
                    return None
                text = r.text
                return text if text and not is_antibot(text) else None
    except Exception:
        pass
    return None


async def _fetch_curl_cffi(url: str, timeout: int) -> str | None:
    loop = asyncio.get_running_loop()
    def _sync() -> str | None:
        try:
            from curl_cffi import requests as cffi_req
            r = cffi_req.get(url, impersonate="chrome124", timeout=timeout, headers={"User-Agent": _UA})
            r.raise_for_status()
            if is_non_text_content_type(r.headers.get("content-type", "")):
                return None
            text = r.text
            return text if text and not is_antibot(text) else None
        except Exception:
            return None
    return await loop.run_in_executor(None, _sync)


async def _fetch_pdf_bytes(url: str, timeout: float, tls_verify: bool = True) -> bytes:
    """Fetch PDF bytes with the shared PDF size ceiling."""
    from core.extract.pdf_extractor import MAX_PDF_BYTES, looks_like_pdf_bytes

    try:
        import httpx
        headers = {"User-Agent": _UA, "Accept": "application/pdf,*/*;q=0.8"}
        async with httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
            verify=tls_verify,
        ) as client:
            async with client.stream("GET", url) as r:
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
    except Exception:
        pass

    loop = asyncio.get_running_loop()

    def _sync() -> bytes:
        try:
            from curl_cffi import requests as cffi_req
            r = cffi_req.get(
                url,
                impersonate="chrome124",
                timeout=int(timeout) + 3,
                headers={"User-Agent": _UA, "Accept": "application/pdf,*/*;q=0.8"},
            )
            data = bytes(r.content or b"")
            if 200 <= r.status_code < 400 and len(data) <= MAX_PDF_BYTES and looks_like_pdf_bytes(data):
                return data
        except Exception:
            return b""
        return b""

    return await loop.run_in_executor(None, _sync)


async def _read_pdf(url: str, timeout: float, tls_verify: bool, max_chars: int) -> str:
    """Fetch and extract a PDF into markdown."""
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


async def _fetch_race(url: str, timeout: float, tls_verify: bool = True) -> str | None:
    """Race httpx vs curl_cffi — first non-antibot response wins, loser cancelled."""
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
                pass
    return result


# ---------------------------------------------------------------------------
# Wayback Machine fallback
# ---------------------------------------------------------------------------

async def _fetch_wayback(url: str, timeout: int = 30) -> str | None:
    """Fetch a page via Wayback Machine as a last-resort fallback."""
    from urllib.parse import quote as _quote
    loop = asyncio.get_running_loop()

    def _do() -> str | None:
        import requests as _req
        cdx_url = (
            "https://web.archive.org/cdx/search/cdx"
            f"?url={_quote(url, safe='')}"
            "&output=json&limit=1&fl=timestamp,statuscode&filter=statuscode:200&fastLatest=true"
        )
        try:
            cdx = _req.get(cdx_url, timeout=timeout,
                           headers={"User-Agent": "Mozilla/5.0 (compatible; WaybackFetcher/1.0)"})
            cdx.raise_for_status()
            rows = cdx.json()
        except Exception:
            return None
        if not rows or len(rows) < 2:
            return None
        ts = rows[1][0]
        snap_url = f"https://web.archive.org/web/{ts}id_/{url}"
        try:
            resp = _req.get(snap_url, timeout=timeout,
                            headers={"User-Agent": "Mozilla/5.0 (compatible; WaybackFetcher/1.0)"},
                            allow_redirects=True)
            resp.raise_for_status()
            if is_non_text_content_type(resp.headers.get("content-type", "")):
                return None
            return resp.text
        except Exception:
            return None

    return await loop.run_in_executor(None, _do)


# ---------------------------------------------------------------------------
# ReadPageService
# ---------------------------------------------------------------------------

@dataclass
class ReadPageOptions:
    timeout: float = 20.0
    use_wayback_fallback: bool = False
    max_chars: int = 20_000


class ReadPageService:
    """Fetch a single page and return clean markdown text."""

    def __init__(self, options: Optional[ReadPageOptions] = None) -> None:
        cfg = load_search_config()
        self._cfg = cfg
        self._opts = options or ReadPageOptions(
            timeout=cfg.extraction.timeout_seconds,
            max_chars=cfg.extraction.max_page_chars,
        )

    async def read(self, url: str) -> str:
        """Fetch a URL and return its content as clean markdown."""
        from core.extract.pdf_extractor import looks_like_pdf_text_dump, looks_like_pdf_url

        opts = self._opts
        url = url.strip()

        logger.info("read_page url=%r", url)

        if _is_skippable(url):
            return f"Error: URL type not supported for text extraction: {url}"

        if _is_youtube(url):
            return await _fetch_youtube_transcript(url)

        if _is_reddit(url):
            try:
                return await _fetch_reddit_json(url)
            except Exception as exc:
                logger.warning("Reddit fetch failed for %s: %s", url, exc)

        if looks_like_pdf_url(url):
            return await _read_pdf(
                url,
                timeout=opts.timeout,
                tls_verify=self._cfg.search.tls_verify,
                max_chars=opts.max_chars,
            )

        cached_page = _cache.get_cached(url)
        if cached_page and _cache.is_fresh(url) and cached_page.raw_html:
            raw_html: str | None = cached_page.raw_html
        else:
            # -- Fetch: httpx + curl_cffi race, Wayback as last resort --
            raw_html = await _fetch_race(url, timeout=opts.timeout, tls_verify=self._cfg.search.tls_verify)

            if not raw_html and opts.use_wayback_fallback:
                raw_html = await _fetch_wayback(url, timeout=30)
            
            if raw_html and not is_antibot(raw_html):
                _cache.cache_page(url, "", clean_text="", raw_html=raw_html)

        if not raw_html:
            return f"Error: Could not fetch content from: {url}"

        if is_antibot(raw_html):
            return (
                f"Error: Anti-bot protection detected on {url}. "
                "Cannot extract content without a browser."
            )

        if looks_like_pdf_text_dump(raw_html):
            return await _read_pdf(
                url,
                timeout=opts.timeout,
                tls_verify=self._cfg.search.tls_verify,
                max_chars=opts.max_chars,
            )

        # -- Normalize --
        markdown = normalize_page(url, raw_html)
        if not markdown or len(markdown.strip()) < self._cfg.extraction.min_content_length:
            return f"Warning: Very little content extracted from: {url}\n\n{markdown}"

        if len(markdown) > opts.max_chars:
            markdown = markdown[:opts.max_chars].rsplit("\n", 1)[0] + "\n\n[...truncated]"

        return markdown


# ---------------------------------------------------------------------------
# Top-level convenience coroutine
# ---------------------------------------------------------------------------

async def run_read_page(
    url: str,
    timeout: float = 20.0,
    use_wayback_fallback: bool = False,
    max_chars: int = 20_000,
) -> str:
    """Convenience entry point for MCP adapter and CLI."""
    opts = ReadPageOptions(
        timeout=timeout,
        use_wayback_fallback=use_wayback_fallback,
        max_chars=max_chars,
    )
    service = ReadPageService(options=opts)
    return await service.read(url)
