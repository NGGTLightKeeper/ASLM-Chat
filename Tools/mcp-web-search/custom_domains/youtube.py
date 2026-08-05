# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse

from core.fetch.thread_pool import io_pool as _io_pool

from custom_domains.base import FetchContext, PageResult

logger = logging.getLogger("custom_domains.youtube")

_YT_HOSTS = ("youtube.com", "youtu.be")


# Normalized host from URL (no www/m prefix).
def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")


# True for YouTube watch/short URLs.
def is_youtube(url: str) -> bool:
    return _host(url) in _YT_HOSTS


# Parse the 11-char YouTube video id from a URL.
def youtube_video_id(url: str) -> str | None:
    m = re.search(r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


# Fetch a YouTube transcript: youtube-transcript-api first, then yt-dlp fallback.
async def fetch_youtube_transcript(url: str) -> str:
    video_id = youtube_video_id(url)
    if not video_id:
        return f"Error: Could not extract video ID from: {url}"

    loop = asyncio.get_running_loop()

    # Attempt 1: youtube-transcript-api (one API call, no file download).
    # Returns transcript text, "ERR:<message>" on known errors, or None to continue.
    def _yta_try() -> str | None:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except ImportError:
            return None

        PREFERRED = ["ru", "en", "uk", "de", "fr"]

        try:
            import requests as _req

            class _TimedSession(_req.Session):
                def request(self, method, url, **kwargs):  # type: ignore[override]
                    kwargs.setdefault("timeout", 15)
                    return super().request(method, url, **kwargs)

            try:
                api = YouTubeTranscriptApi(http_client=_TimedSession())
            except TypeError:
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
            return None

        fetched = None
        for lang in PREFERRED:
            try:
                fetched = transcript_list.find_manually_created_transcript([lang])
                break
            except Exception:
                logger.debug("Manual transcript unavailable for %s lang=%s", url, lang)
                continue

        if fetched is None:
            for lang in PREFERRED:
                try:
                    fetched = transcript_list.find_generated_transcript([lang])
                    break
                except Exception:
                    logger.debug("Generated transcript unavailable for %s lang=%s", url, lang)
                    continue

        if fetched is None:
            try:
                fetched = next(iter(transcript_list))
                if fetched.language_code not in PREFERRED:
                    try:
                        fetched = fetched.translate("en")
                    except Exception:
                        logger.debug("Transcript translation failed for %s from %s", url, fetched.language_code)
                        pass
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

    result = await loop.run_in_executor(_io_pool, _yta_try)
    if result and result.startswith("ERR:"):
        return f"Error: {result[4:]}"
    if result:
        return result

    # Attempt 2: yt-dlp (heavier — downloads subtitle files).
    def _yt_dlp_try() -> str | None:
        try:
            import glob as _glob
            import os
            import tempfile

            import yt_dlp

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
                    "socket_timeout": 15,
                    "retries": 1,
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

    result = await loop.run_in_executor(_io_pool, _yt_dlp_try)
    return result or f"Error: No transcript available for: {url}"


# Unified handler: return a YouTube video transcript as markdown text.
class YouTubeHandler:
    name = "youtube"
    fallback_to_generic = False
    scope = "read_page"  # requires a browser; not for web_search inline parsing

    # True for YouTube watch/short URLs.
    def matches(self, url: str) -> bool:
        return is_youtube(url)

    # Fetch the transcript; errors are returned verbatim (terminal, no fallback).
    async def read(self, url: str, ctx: FetchContext) -> PageResult:
        markdown = await fetch_youtube_transcript(url)
        ok = bool(markdown) and not markdown.startswith("Error:")
        return PageResult(
            markdown=markdown,
            ok=ok,
            method="youtube_transcript",
            error="" if ok else markdown,
        )


HANDLER = YouTubeHandler()
