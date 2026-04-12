# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Camoufox fetcher — async interface to the isolated Camoufox subprocess worker.

Unlike PageFetcher (httpx → curl_cffi), this fetcher routes every request
through an isolated child process so the Playwright/asyncio internals of
Camoufox never interfere with the MCP server's event loop.

Public API
----------
is_camoufox_available() -> bool
fetch_with_camoufox(url, *, ...) -> FetchResult
fetch_batch_with_camoufox(urls, *, ...) -> list[FetchResult]
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("core.fetch.camoufox_fetcher")

# Path to the worker script (same package directory).
_WORKER_SCRIPT = Path(__file__).parent / "_camoufox_worker.py"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class FetchResult:
    """Result from a Camoufox fetch attempt."""

    url: str
    success: bool = False
    html: str = ""
    text: str = ""           # normalised text (populated after normalisation)
    title: str = ""
    method: str = "camoufox"
    error: str = ""
    duration_sec: float = 0.0


# ---------------------------------------------------------------------------
# Availability check (cached)
# ---------------------------------------------------------------------------

_available_cache: Optional[bool] = None


def is_camoufox_available() -> bool:
    """Return True if the camoufox package and its browser binary exist."""
    global _available_cache
    if _available_cache is not None:
        return _available_cache

    try:
        import camoufox  # noqa: F401
        from camoufox.pkgman import INSTALL_DIR, LAUNCH_FILE, OS_NAME

        launch_rel = LAUNCH_FILE.get(OS_NAME)
        if not launch_rel:
            _available_cache = False
            return False

        install_dir = Path(str(INSTALL_DIR))
        if OS_NAME == "mac":
            launch_path = (
                install_dir / "Camoufox.app" / "Contents" / "Resources" / launch_rel
            ).resolve()
        else:
            launch_path = install_dir / launch_rel

        _available_cache = launch_path.exists()
        if not _available_cache:
            logger.debug("camoufox binary not found at %s", launch_path)
    except Exception as exc:
        logger.debug("camoufox not available: %s", exc)
        _available_cache = False

    return bool(_available_cache)


# ---------------------------------------------------------------------------
# Single URL fetch via subprocess
# ---------------------------------------------------------------------------

async def fetch_with_camoufox(
    url: str,
    *,
    wait_sec: float = 4.0,
    headless: bool = True,
    humanize: bool = True,
    geoip: bool = False,
    locale: str = "en-US",
    proxy: Optional[dict] = None,
    warmup_urls: Optional[list[str]] = None,
    warmup_count: int = 1,
    timeout_sec: float = 45.0,
    process_timeout: float = 0.0,   # wall-clock timeout for the child process; 0 = timeout_sec + 15
    normalize: bool = True,          # run page_normalizer on raw HTML
) -> FetchResult:
    """Fetch *url* in an isolated Camoufox subprocess.

    Returns a FetchResult. On failure, FetchResult.success is False and
    FetchResult.error contains the reason.
    """
    t0 = time.perf_counter()

    if not process_timeout:
        process_timeout = timeout_sec + 15.0

    payload = {
        "url": url,
        "wait_sec": wait_sec,
        "headless": headless,
        "humanize": humanize,
        "geoip": geoip,
        "locale": locale,
        "proxy": proxy,
        "warmup_urls": warmup_urls or ["https://www.wikipedia.org/"],
        "warmup_count": warmup_count,
        "timeout_sec": timeout_sec,
    }
    payload_bytes = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(_WORKER_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except Exception as exc:
        return FetchResult(url=url, error=f"failed to start worker: {exc}",
                           duration_sec=time.perf_counter() - t0)

    try:
        stdout_bytes, _ = await asyncio.wait_for(
            proc.communicate(input=payload_bytes),
            timeout=process_timeout,
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return FetchResult(
            url=url,
            error=f"worker timeout after {process_timeout:.0f}s",
            duration_sec=time.perf_counter() - t0,
        )
    except Exception as exc:
        try:
            proc.kill()
        except Exception:
            pass
        return FetchResult(url=url, error=f"worker communicate error: {exc}",
                           duration_sec=time.perf_counter() - t0)

    duration = time.perf_counter() - t0

    if not stdout_bytes:
        return FetchResult(url=url, error="worker produced no output", duration_sec=duration)

    try:
        data = json.loads(stdout_bytes.decode("utf-8", errors="replace").strip())
    except json.JSONDecodeError as exc:
        return FetchResult(url=url, error=f"bad JSON from worker: {exc}", duration_sec=duration)

    if not data.get("ok"):
        return FetchResult(
            url=url,
            error=str(data.get("error", "unknown worker error")),
            duration_sec=duration,
        )

    raw_html: str = data.get("html", "")
    title: str = data.get("title", "")

    if not raw_html or len(raw_html) < 200:
        return FetchResult(url=url, error="insufficient HTML content", duration_sec=duration)

    # Check for anti-bot wall.
    try:
        from core.fetch.antibot import is_antibot
        if is_antibot(raw_html):
            return FetchResult(url=url, error="antibot wall detected", duration_sec=duration)
    except Exception:
        pass

    # Optionally normalise HTML → clean text.
    clean_text = ""
    if normalize:
        try:
            loop = asyncio.get_running_loop()
            from core.extract.page_normalizer import normalize_page
            clean_text = await loop.run_in_executor(
                None, lambda: normalize_page(url, raw_html, "")
            )
        except Exception as exc:
            logger.debug("page_normalizer failed for %s: %s", url, exc)

    logger.info(
        "camoufox_fetcher: %s -> ok html=%d text=%d dur=%.1fs",
        url, len(raw_html), len(clean_text), duration,
    )

    return FetchResult(
        url=url,
        success=True,
        html=raw_html,
        text=clean_text,
        title=title,
        method="camoufox",
        duration_sec=duration,
    )


# ---------------------------------------------------------------------------
# Batch fetch
# ---------------------------------------------------------------------------

async def fetch_batch_with_camoufox(
    urls: list[str],
    *,
    max_concurrency: int = 2,
    timeout_sec: float = 45.0,
    process_timeout: float = 0.0,
    wait_sec: float = 4.0,
    headless: bool = True,
    humanize: bool = True,
    geoip: bool = False,
    locale: str = "en-US",
    proxy: Optional[dict] = None,
    warmup_urls: Optional[list[str]] = None,
    warmup_count: int = 1,
    normalize: bool = True,
) -> list[FetchResult]:
    """Fetch multiple URLs via Camoufox with limited concurrency.

    Camoufox is heavy (full browser per request), so keep max_concurrency
    at 1-2 for stable operation.
    """
    if not urls:
        return []

    sem = asyncio.Semaphore(max_concurrency)

    async def _one(url: str) -> FetchResult:
        async with sem:
            return await fetch_with_camoufox(
                url,
                wait_sec=wait_sec,
                headless=headless,
                humanize=humanize,
                geoip=geoip,
                locale=locale,
                proxy=proxy,
                warmup_urls=warmup_urls,
                warmup_count=warmup_count,
                timeout_sec=timeout_sec,
                process_timeout=process_timeout,
                normalize=normalize,
            )

    tasks = [_one(u) for u in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    out: list[FetchResult] = []
    for url, r in zip(urls, results):
        if isinstance(r, Exception):
            out.append(FetchResult(url=url, error=str(r)))
        else:
            out.append(r)
    return out
