# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Overdrive Mode orchestrator for mcp-web-search.

When enabled, _read_url_overdrive replaces the default read flow with a
multi-method race:

  Phase A  — httpx + curl_cffi (fast, parallel)
  Phase B  — Camoufox Firefox + Patchright Chromium (browser-based, heavier)
  Fallback — Tesseract OCR on a browser screenshot (last resort)

The first method that returns a valid result wins; the rest are cancelled.
"""

from __future__ import annotations

import asyncio
import io
import logging
import random
import re
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
PROJECT_DIR = _HERE.parent
DEEP_RESEARCH_DIR = PROJECT_DIR / "deep-research"

if DEEP_RESEARCH_DIR.exists():
    deep_research_path = str(DEEP_RESEARCH_DIR)
    if deep_research_path not in sys.path:
        sys.path.insert(0, deep_research_path)

try:
    from .. import config as _ws_config
except (ImportError, ValueError):
    try:
        import config as _ws_config
    except ImportError:
        _ws_config = None

try:
    from src.domain_registry import DomainRegistry as _DomainRegistry
    _domain_registry = _DomainRegistry()
except Exception:
    _domain_registry = None

_TRACE_BROWSERS = bool(
    getattr(_ws_config, "OVERDRIVE_TRACE_BROWSERS", None)
    if _ws_config is not None
    else os.getenv("SEARCH_OVERDRIVE_TRACE_BROWSERS", "true").lower() == "true"
)


def _trace_browser(message: str) -> None:
    if _TRACE_BROWSERS:
        print(message, file=sys.stderr, flush=True)

# ---------------------------------------------------------------------------
# Optional dependency probes
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


# ---------------------------------------------------------------------------
# Validity checker
# ---------------------------------------------------------------------------

_BLOCK_MARKERS = (
    "access denied",
    "403 forbidden",
    "cloudflare",
    "just a moment",
    "checking your browser",
    "enable javascript",
)


def _is_valid_text(text: str) -> bool:
    """Return True when *text* looks like real page content."""
    stripped = text.strip()
    if len(stripped) <= 150:
        return False
    lowered = stripped[:2000].lower()
    for marker in _BLOCK_MARKERS:
        if marker in lowered:
            return False
    return True


# ---------------------------------------------------------------------------
# HTML → plain-text helper
# ---------------------------------------------------------------------------

def _html_to_text(raw_html: str) -> str:
    """Cheap tag-stripping to get readable text from HTML."""
    raw = re.sub(
        r"<(script|style)[^>]*>.*?</\1>", "", raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return re.sub(r"\s{2,}", "\n", re.sub(r"<[^>]+>", " ", raw)).strip()


# ---------------------------------------------------------------------------
# Fetch methods — Level 1
# ---------------------------------------------------------------------------

async def _fetch_httpx(url: str, timeout: float = 15.0) -> str:
    """Method 1: plain httpx GET."""
    import httpx

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36"
            )
        },
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return _html_to_text(resp.text)


async def _fetch_curl_cffi(url: str, timeout: int = 15) -> str:
    """Method 2: curl_cffi with Chrome TLS fingerprint."""
    from curl_cffi import requests as cffi_requests

    loop = asyncio.get_running_loop()

    def _do():
        r = cffi_requests.get(
            url,
            impersonate="chrome124",
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36"
                )
            },
        )
        r.raise_for_status()
        return r.text

    raw = await loop.run_in_executor(None, _do)
    return _html_to_text(raw)


async def _fetch_preview_bot(url: str, timeout: int = 15) -> str:
    """Method 2.5: social-media bot UA probe via preview_bot_fetcher."""
    try:
        from preview_bot_fetcher import probe_with_preview_bots
    except ImportError:
        from .preview_bot_fetcher import probe_with_preview_bots  # type: ignore
    return await probe_with_preview_bots(url, timeout=timeout)


def _domain_info(url: str):
    if _domain_registry is None:
        return None
    try:
        return _domain_registry.lookup(url)
    except Exception:
        return None


async def _fetch_camoufox_overdrive(
    url: str,
    human_behavior: bool = True,
    timeout_sec: int = 30,
    idle_timeout_sec: float | None = None,
) -> tuple[str, Optional[bytes]]:
    """Method 3: standalone Camoufox (Firefox).

    Returns ``(text, screenshot_bytes | None)``.
    """
    loop = asyncio.get_running_loop()

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
                    await page.goto(
                        url,
                        wait_until="networkidle",
                        timeout=timeout_sec * 1000,
                    )

                    if human_behavior:
                        await asyncio.sleep(random.uniform(0.5, 2.0))
                        scroll_px = random.randint(200, 600)
                        await page.mouse.move(
                            random.randint(100, 400),
                            random.randint(100, 300),
                        )
                        await page.mouse.move(
                            random.randint(400, 800),
                            random.randint(200, 500),
                        )
                        await page.evaluate(
                            f"window.scrollBy(0, {scroll_px})"
                        )
                        await asyncio.sleep(random.uniform(0.3, 0.8))

                    text = await page.inner_text("body")
                    try:
                        screenshot = await page.screenshot(type="png")
                    except Exception:
                        pass
                    return text, screenshot
                finally:
                    await page.close()

        if idle_timeout_sec and idle_timeout_sec > 0:
            return _aio.run(_aio.wait_for(_do(), timeout=idle_timeout_sec))
        return _aio.run(_do())

    return await loop.run_in_executor(None, _run_in_thread)


async def _fetch_patchright(
    url: str,
    timeout_sec: int = 30,
    idle_timeout_sec: float | None = None,
) -> tuple[str, Optional[bytes]]:
    """Method 4: Patchright Chromium.

    Returns ``(text, screenshot_bytes | None)``.
    """
    if not _PATCHRIGHT_AVAILABLE:
        return "", None

    async def _do():
        pw = await _patchright_playwright()
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=timeout_sec * 1000)
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

    if idle_timeout_sec and idle_timeout_sec > 0:
        return await asyncio.wait_for(_do(), timeout=idle_timeout_sec)
    return await _do()


# ---------------------------------------------------------------------------
# Level 2 — OCR fallback
# ---------------------------------------------------------------------------

async def _fetch_ocr_fallback(screenshot_bytes: bytes, timeout: float = 30.0) -> str:
    """Method 5: Tesseract OCR on a browser screenshot."""
    if not _OCR_AVAILABLE or not screenshot_bytes:
        return ""

    loop = asyncio.get_running_loop()

    def _do_ocr():
        image = Image.open(io.BytesIO(screenshot_bytes))
        return pytesseract.image_to_string(image, lang="eng+rus")

    return await asyncio.wait_for(
        loop.run_in_executor(None, _do_ocr),
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

# Shared semaphore limits concurrent browser instances across requests.
_browser_semaphore: asyncio.Semaphore | None = None


def _get_browser_semaphore(concurrency: int) -> asyncio.Semaphore:
    """Lazy-init a module-level semaphore for browser concurrency."""
    global _browser_semaphore
    if _browser_semaphore is None:
        _browser_semaphore = asyncio.Semaphore(concurrency)
    return _browser_semaphore


async def read_url_overdrive(
    url: str,
    *,
    human_behavior: bool = True,
    ocr_fallback: bool = True,
    parallel_timeout: float = 20.0,
    ocr_timeout: float = 30.0,
    browser_start_delay: float = 0.75,
    browser_concurrency: int = 2,
    browser_fanout: int | None = None,
    browser_idle_timeout: float | None = None,
    char_budget: int = 15_000,
) -> str:
    """Overdrive page-read orchestrator.

    Runs a staggered race of up to four fetch methods and returns the first
    valid result.  Falls back to OCR if all methods fail.
    """

    if browser_fanout is None:
        browser_fanout = int(getattr(_ws_config, "OVERDRIVE_BROWSER_FANOUT", 4))
    browser_fanout = max(1, int(browser_fanout))
    if browser_idle_timeout is None:
        browser_idle_timeout = float(getattr(_ws_config, "OVERDRIVE_BROWSER_IDLE_TIMEOUT", 30.0))
    sem = _get_browser_semaphore(browser_concurrency)
    info = _domain_info(url)

    # ------------------------------------------------------------------
    # Wrap each fetch method so we can track validity and screenshots
    # ------------------------------------------------------------------

    best_screenshot: bytes | None = None
    result_text: str | None = None
    done_event = asyncio.Event()

    async def _race_fast(coro, label: str):
        """Run a fast (HTTP-only) fetch and check validity."""
        nonlocal result_text
        try:
            text = await coro
            if _is_valid_text(text):
                if result_text is None:
                    result_text = text
                    done_event.set()
                    logger.debug("overdrive: winner=%s", label)
                    _trace_browser(f"[overdrive] winner={label} url={url}")
        except Exception as exc:
            logger.debug("overdrive: %s failed: %s", label, exc)

    async def _race_browser(coro_fn, label: str):
        """Run a browser fetch behind the concurrency semaphore.

        Accepts a zero-argument callable that *creates* the coroutine so the
        coroutine object is only instantiated after the semaphore is acquired.
        This avoids "coroutine was never awaited" warnings when the task is
        cancelled before it starts.
        """
        nonlocal result_text, best_screenshot
        async with sem:
            try:
                _trace_browser(f"[overdrive] launching {label} url={url}")
                if browser_idle_timeout and browser_idle_timeout > 0:
                    text, screenshot = await asyncio.wait_for(coro_fn(), timeout=browser_idle_timeout)
                else:
                    text, screenshot = await coro_fn()
                if screenshot and best_screenshot is None:
                    best_screenshot = screenshot
                if _is_valid_text(text):
                    if result_text is None:
                        result_text = text
                        done_event.set()
                        logger.debug("overdrive: winner=%s", label)
                        _trace_browser(f"[overdrive] winner={label} url={url}")
            except asyncio.TimeoutError:
                logger.debug("overdrive: %s timed out after %.1fs idle", label, browser_idle_timeout)
                _trace_browser(f"[overdrive] timeout={label} idle={browser_idle_timeout:.1f}s url={url}")
            except Exception as exc:
                logger.debug("overdrive: %s failed: %s", label, exc)

    # ------------------------------------------------------------------
    # Phase A — fast methods
    # ------------------------------------------------------------------
    fast_tasks = [
        asyncio.create_task(_race_fast(_fetch_httpx(url), "httpx")),
        asyncio.create_task(_race_fast(_fetch_curl_cffi(url), "curl_cffi")),
    ]
    mimic_user_agent = bool(getattr(_ws_config, "MIMIC_USER_AGENT", True))
    if mimic_user_agent and getattr(info, "try_preview_bot", False):
        fast_tasks.append(
            asyncio.create_task(_race_fast(_fetch_preview_bot(url), "preview_bot"))
        )

    # Give the fast methods a short head-start.
    try:
        await asyncio.wait_for(done_event.wait(), timeout=browser_start_delay)
    except asyncio.TimeoutError:
        pass

    if result_text is not None:
        # Fast method already won — cancel leftovers and return.
        for t in fast_tasks:
            t.cancel()
        return result_text[:char_budget]

    # ------------------------------------------------------------------
    # Phase B — browser methods (always launch in parallel with fast)
    # ------------------------------------------------------------------
    browser_tasks: list[asyncio.Task] = []
    browser_factories: list[tuple[str, callable]] = [
        (
            "camoufox",
            lambda: _fetch_camoufox_overdrive(
                url,
                human_behavior=human_behavior,
                idle_timeout_sec=browser_idle_timeout,
            ),
        ),
    ]
    if _PATCHRIGHT_AVAILABLE:
        browser_factories.append(
            (
                "patchright",
                lambda: _fetch_patchright(url, idle_timeout_sec=browser_idle_timeout),
            )
        )

    launch_plan: list[tuple[str, callable]] = []
    while len(launch_plan) < browser_fanout:
        for label, factory in browser_factories:
            launch_plan.append((label, factory))
            if len(launch_plan) >= browser_fanout:
                break

    _trace_browser(
        "[overdrive] browser_plan "
        f"url={url} slots={len(launch_plan)} plan="
        + ", ".join(
            f"{label}#{idx + 1}" for idx, (label, _factory) in enumerate(launch_plan)
        )
    )

    browser_counts: dict[str, int] = {}
    for label, factory in launch_plan:
        browser_counts[label] = browser_counts.get(label, 0) + 1
        suffix = browser_counts[label]
        browser_tasks.append(
            asyncio.create_task(
                _race_browser(factory, f"{label}#{suffix}")
            )
        )

    all_tasks = fast_tasks + browser_tasks

    # ------------------------------------------------------------------
    # Wait for the first valid result or timeout
    # ------------------------------------------------------------------
    try:
        await asyncio.wait_for(done_event.wait(), timeout=parallel_timeout)
    except asyncio.TimeoutError:
        pass

    # Cancel remaining tasks.
    for t in all_tasks:
        if not t.done():
            t.cancel()
    # Await them to ensure cleanup runs.
    await asyncio.gather(*all_tasks, return_exceptions=True)

    if result_text is not None:
        return result_text[:char_budget]

    # ------------------------------------------------------------------
    # Phase B.5 — WARP SOCKS5 proxy fallback
    # ------------------------------------------------------------------
    try:
        from warp_manager import fetch_via_warp_auto
    except ImportError:
        try:
            from .warp_manager import fetch_via_warp_auto  # type: ignore
        except ImportError:
            fetch_via_warp_auto = None  # type: ignore

    should_try_warp = bool(
        getattr(_ws_config, "WARP_ENABLED", True)
        and (
            getattr(info, "use_warp", False)
            or getattr(_ws_config, "WARP_ALL_FAILURES", False)
        )
    )
    if fetch_via_warp_auto is not None and should_try_warp:
        try:
            _trace_browser(f"[overdrive] launching warp url={url}")
            warp_text = await asyncio.wait_for(
                fetch_via_warp_auto(url, timeout=int(parallel_timeout)),
                timeout=parallel_timeout + 5,
            )
            if _is_valid_text(warp_text):
                logger.debug("overdrive: winner=warp")
                _trace_browser(f"[overdrive] winner=warp url={url}")
                return warp_text[:char_budget]
        except Exception as exc:
            logger.debug("overdrive: WARP failed: %s", exc)

    # ------------------------------------------------------------------
    # Phase C — OCR fallback
    # ------------------------------------------------------------------
    if ocr_fallback and _OCR_AVAILABLE and best_screenshot:
        try:
            _trace_browser(f"[overdrive] launching ocr url={url}")
            ocr_text = await _fetch_ocr_fallback(
                best_screenshot, timeout=ocr_timeout,
            )
            if _is_valid_text(ocr_text):
                logger.debug("overdrive: winner=ocr")
                _trace_browser(f"[overdrive] winner=ocr url={url}")
                return ocr_text[:char_budget]
        except Exception as exc:
            logger.debug("overdrive: OCR failed: %s", exc)

    # ------------------------------------------------------------------
    # Nothing worked — return empty string (caller handles the error)
    # ------------------------------------------------------------------
    _trace_browser(f"[overdrive] all_failed url={url}")
    logger.debug("overdrive: all methods failed for %s", url)
    return ""
