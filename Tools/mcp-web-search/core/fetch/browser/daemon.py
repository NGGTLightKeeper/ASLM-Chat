# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Persistent, supervised warm-browser daemon (chromium / cloakbrowser only).

Keeps one stealth Chromium warm in-process and serves page fetches over a small HTTP
API, so callers pay the cold-start cost once. Chromium-only by design — it is the sole
browser backend in web search.

Supervision (the part the original throwaway prototype lacked):
  * one identity context seeded from the IdentityStore on launch (earned cookies /
    storageState carry across restarts);
  * idle checkpoints — every checkpoint_interval, if no fetch is in flight and the
    state is dirty, export storageState back to the store;
  * recycle on request-count / age / RSS of the browser process tree, each preceded by
    a forced checkpoint; a burn (blocked streak) rotates identity instead of restoring.

Run:
  python -m core.fetch.browser.daemon --port 8765
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import unquote, urlparse

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from aiohttp import web

from core.fetch.antibot import is_antibot
from core.fetch.browser.identity_store import IdentityStore, get_identity_store
from core.logging_setup import setup_logging

logger = logging.getLogger("core.fetch.browser.daemon")

_MIN_TEXT_CHARS = 200
_MIN_HTML_CHARS = 200
# Consecutive blocked fetches that flip a recycle from "restore" to "rotate identity".
_BURN_STREAK = 3


# Why the warm browser was torn down — drives whether identity is restored or rotated.
class RecycleReason:
    REQUESTS = "requests"
    AGE = "age"
    RSS = "rss"
    BURN = "burn"


# Outcome of a single page fetch through the warm browser (mirrors client BrowserFetch).
@dataclass
class ScrapeResult:
    url: str
    status: str = "error"      # ok | blocked | timeout | error
    ok: bool = False
    title: str = ""
    html: str = ""
    text: str = ""
    engine: str = "chromium"
    ms: float = 0.0
    error: str = ""


# Parse a proxy URL into the cloakbrowser shape.
def _parse_proxy(proxy_url: str | None) -> Optional[str]:
    if not proxy_url:
        return None
    parsed = urlparse(proxy_url)
    if not parsed.scheme or not parsed.hostname:
        return None
    return proxy_url


# Resident memory of this process plus its children (the chromium tree), in MB.
def _process_tree_rss_mb() -> float:
    try:
        import psutil
    except Exception:  # noqa: BLE001 — psutil optional; without it RSS recycle is skipped
        return 0.0
    try:
        proc = psutil.Process()
        total = proc.memory_info().rss
        for child in proc.children(recursive=True):
            try:
                total += child.memory_info().rss
            except Exception:  # noqa: BLE001
                continue
        return total / (1024 * 1024)
    except Exception as exc:  # noqa: BLE001
        logger.debug("rss measurement failed: %s", exc)
        return 0.0


# One warm Chromium with its identity context, recycle policy and checkpoint discipline.
class WarmChromium:
    name = "chromium"

    def __init__(
        self,
        *,
        identity: IdentityStore,
        family: str = "chromium",
        headless: bool = True,
        humanize: bool = False,
        locale: str = "en-US",
        proxy: str | None = None,
        max_requests: int = 40,
        max_age_sec: float = 900.0,
        max_rss_mb: int = 2048,
        checkpoint_interval: float = 30.0,
        nav_timeout: float = 30.0,
        wait: float = 3.0,
    ) -> None:
        self._identity = identity
        self._family = family
        self.headless = headless
        self.humanize = humanize
        self.locale = locale
        self.proxy = proxy
        self.max_requests = max(1, int(max_requests))
        self.max_age = max(1.0, float(max_age_sec))
        self.max_rss_mb = max(256, int(max_rss_mb))
        self.checkpoint_interval = max(5.0, float(checkpoint_interval))
        self.nav_timeout = max(1.0, float(nav_timeout))
        self.wait = max(0.0, float(wait))

        self._lock = asyncio.Lock()
        self._browser: Any | None = None
        self._context: Any | None = None
        self._teardown: Callable[[], Awaitable[None]] | None = None
        self._started_at = 0.0
        self._last_used = 0.0
        self._requests = 0
        self._total = 0
        self._recycles = 0
        self._blocked_streak = 0
        self._dirty = False              # state changed since last checkpoint
        self._inflight = 0
        self._checkpoint_task: asyncio.Task | None = None

    # ── lifecycle ────────────────────────────────────────────────────────────────

    # Launch chromium and open a context seeded with the family's latest good identity.
    async def _open(self) -> None:
        import cloakbrowser

        browser = await cloakbrowser.launch_async(
            headless=self.headless,
            stealth_args=True,
            humanize=self.humanize,
            locale=self.locale,
            proxy=self.proxy,
        )
        seed = self._identity.latest_good(self._family)
        try:
            context = await browser.new_context(storage_state=seed) if seed else await browser.new_context()
        except Exception:  # noqa: BLE001 — fall back to the default context if seeding fails
            context = await browser.new_context()

        async def _close() -> None:
            try:
                await context.close()
            finally:
                await browser.close()

        self._browser, self._context, self._teardown = browser, context, _close
        self._started_at = time.monotonic()
        self._requests = 0
        self._dirty = False

    # Launch if down.
    async def _ensure(self) -> None:
        if self._browser is None:
            await self._open()

    # Export storageState into the store (best-effort; needs a live, quiet browser).
    async def _checkpoint(self, *, good: bool = True) -> None:
        if self._context is None:
            return
        try:
            state = await asyncio.wait_for(self._context.storage_state(), timeout=10.0)
        except Exception as exc:  # noqa: BLE001
            logger.debug("checkpoint export failed: %s", exc)
            return
        self._identity.checkpoint(self._family, state, good=good)
        self._dirty = False

    # Tear the browser down (optionally checkpointing first).
    async def _shutdown_browser(self, *, checkpoint: bool, good: bool = True) -> None:
        if checkpoint:
            await self._checkpoint(good=good)
        if self._teardown is not None:
            try:
                await self._teardown()
            except Exception:  # noqa: BLE001
                pass
        self._browser = self._context = self._teardown = None

    # Decide whether to recycle, returning the reason or None. Pure given current counters.
    def _recycle_reason(self) -> str | None:
        if self._browser is None:
            return None
        if self._blocked_streak >= _BURN_STREAK:
            return RecycleReason.BURN
        if self._requests >= self.max_requests:
            return RecycleReason.REQUESTS
        if (time.monotonic() - self._started_at) >= self.max_age:
            return RecycleReason.AGE
        if self.max_rss_mb and _process_tree_rss_mb() >= self.max_rss_mb:
            return RecycleReason.RSS
        return None

    # Recycle the browser: checkpoint (or rotate on burn), respawn, reseed.
    async def _recycle(self, reason: str) -> None:
        logger.info("recycling warm chromium reason=%s requests=%d", reason, self._requests)
        if reason == RecycleReason.BURN:
            # Poisoned identity: mark it burned and drop to an older good generation / seed.
            await self._shutdown_browser(checkpoint=True, good=False)
            self._identity.rotate(self._family)
        else:
            await self._shutdown_browser(checkpoint=True, good=True)
        self._recycles += 1
        self._blocked_streak = 0
        await self._open()

    # ── fetch ────────────────────────────────────────────────────────────────────

    # Open a page, navigate, wait for content to settle, and scrape it.
    async def _scrape(self, url: str, *, wait: float, nav_timeout: float) -> ScrapeResult:
        page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=int(nav_timeout * 1000))
            if wait > 0:
                try:
                    await page.wait_for_function(
                        f"document.body && document.body.innerText.trim().length > {_MIN_TEXT_CHARS}",
                        timeout=int(wait * 1000),
                    )
                except Exception:  # noqa: BLE001
                    await asyncio.sleep(min(wait, 1.5))
            html = await page.content()
            text = await page.evaluate("document.body ? document.body.innerText : ''") or ""
            title = await page.title()
        finally:
            try:
                await page.close()
            except Exception:  # noqa: BLE001
                pass

        if len(html) < _MIN_HTML_CHARS:
            return ScrapeResult(url=url, status="error", error="insufficient HTML")
        if is_antibot(html):
            return ScrapeResult(url=url, status="blocked", title=title, html=html, text=text)
        return ScrapeResult(url=url, status="ok", ok=True, title=title, html=html, text=text)

    # Fetch one URL through the warm browser, recycling first if a threshold was crossed.
    async def fetch(self, url: str, *, wait: float | None = None,
                    nav_timeout: float | None = None) -> ScrapeResult:
        t0 = time.perf_counter()
        async with self._lock:
            reason = self._recycle_reason()
            if reason is not None:
                await self._recycle(reason)
            await self._ensure()
            self._inflight += 1
            try:
                result = await self._scrape(
                    url,
                    wait=self.wait if wait is None else wait,
                    nav_timeout=self.nav_timeout if nav_timeout is None else nav_timeout,
                )
            except (TimeoutError, asyncio.TimeoutError):
                result = ScrapeResult(url=url, status="timeout", error="navigation timeout")
            except Exception as exc:  # noqa: BLE001 — a crash usually kills the browser
                await self._shutdown_browser(checkpoint=False)
                result = ScrapeResult(url=url, status="error", error=f"{type(exc).__name__}: {exc}")
            finally:
                self._inflight -= 1
            self._requests += 1
            self._total += 1
            self._last_used = time.monotonic()
            self._dirty = True
            self._blocked_streak = self._blocked_streak + 1 if result.status == "blocked" else 0
        result.ms = round((time.perf_counter() - t0) * 1000, 1)
        return result

    # ── supervision ────────────────────────────────────────────────────────────────

    # Eagerly warm the browser and start the idle-checkpoint loop.
    async def start(self) -> None:
        async with self._lock:
            await self._ensure()
        self._checkpoint_task = asyncio.create_task(self._idle_checkpoint_loop(), name="bg:checkpoint")

    # Periodically checkpoint identity while the browser is idle and state is dirty.
    async def _idle_checkpoint_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.checkpoint_interval)
                if self._inflight == 0 and self._dirty and self._browser is not None:
                    async with self._lock:
                        if self._inflight == 0 and self._dirty:
                            await self._checkpoint(good=True)
        except asyncio.CancelledError:
            pass

    # Final checkpoint, stop the loop, tear the browser down.
    async def stop(self) -> None:
        if self._checkpoint_task is not None:
            self._checkpoint_task.cancel()
            try:
                await self._checkpoint_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        async with self._lock:
            await self._shutdown_browser(checkpoint=True, good=True)

    # Runtime snapshot for /health.
    def health(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            "engine": self.name,
            "alive": self._browser is not None,
            "requests_since_recycle": self._requests,
            "total_served": self._total,
            "recycles": self._recycles,
            "blocked_streak": self._blocked_streak,
            "rss_mb": round(_process_tree_rss_mb(), 1),
            "age_sec": round(now - self._started_at, 1) if self._browser is not None else None,
            "idle_sec": round(now - self._last_used, 1) if self._last_used else None,
            "max_requests": self.max_requests,
            "max_age_sec": self.max_age,
            "max_rss_mb": self.max_rss_mb,
        }


# ── HTTP API ──────────────────────────────────────────────────────────────────────

class BrowserDaemon:
    def __init__(self, args: argparse.Namespace) -> None:
        self.browser = WarmChromium(
            identity=get_identity_store(),
            headless=args.headless,
            humanize=args.humanize,
            locale=args.locale,
            proxy=_parse_proxy(args.proxy),
            max_requests=args.max_requests,
            max_age_sec=args.max_age,
            max_rss_mb=args.max_rss_mb,
            checkpoint_interval=args.checkpoint_interval,
            nav_timeout=args.nav_timeout,
            wait=args.wait,
        )
        self.idle_shutdown_sec = max(0.0, float(getattr(args, "idle_shutdown_sec", 0.0)))
        self._stop_event = asyncio.Event()
        self._started_at = time.monotonic()
        self._idle_task: asyncio.Task | None = None

    async def start(self) -> None:
        logger.info("daemon starting chromium ...")
        await self.browser.start()
        logger.info("daemon chromium ready")
        if self.idle_shutdown_sec > 0:
            self._idle_task = asyncio.create_task(self._idle_monitor(), name="bg:idle-shutdown")

    # Self-terminate after idle_shutdown_sec without a served fetch (0 = eternal).
    async def _idle_monitor(self) -> None:
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(min(30.0, self.idle_shutdown_sec))
                last = self.browser._last_used or self._started_at
                idle = time.monotonic() - last
                if self.browser._inflight == 0 and idle >= self.idle_shutdown_sec:
                    logger.info("idle %.0fs >= %.0fs — shutting down", idle, self.idle_shutdown_sec)
                    self._stop_event.set()
                    return
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        if self._idle_task is not None:
            self._idle_task.cancel()
        await self.browser.stop()

    # POST /fetch {url, wait_ms?, timeout_ms?, html?} -> ScrapeResult json.
    async def handle_fetch(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            return web.json_response({"error": "invalid JSON body"}, status=400)
        url = str(data.get("url") or "").strip()
        if not url:
            return web.json_response({"error": "missing 'url'"}, status=400)
        wait = float(data["wait_ms"]) / 1000 if "wait_ms" in data else None
        nav_timeout = float(data["timeout_ms"]) / 1000 if "timeout_ms" in data else None
        result = await self.browser.fetch(url, wait=wait, nav_timeout=nav_timeout)
        logger.info(
            "fetch status=%s ms=%.0f html=%d recycles=%d req=%d url=%r",
            result.status, result.ms, len(result.html), self.browser._recycles,
            self.browser._requests, url[:200],
        )
        payload = asdict(result)
        if data.get("html") is False:
            payload.pop("html", None)
        return web.json_response(payload, status=200 if result.ok else 502)

    async def handle_health(self, _request: web.Request) -> web.Response:
        return web.json_response({"engines": [self.browser.health()]})

    async def handle_shutdown(self, _request: web.Request) -> web.Response:
        self._stop_event.set()
        return web.json_response({"stopping": True})

    def make_app(self) -> web.Application:
        app = web.Application(client_max_size=16 * 1024 * 1024)
        app.add_routes([
            web.post("/fetch", self.handle_fetch),
            web.get("/health", self.handle_health),
            web.post("/shutdown", self.handle_shutdown),
        ])
        return app


async def _serve(args: argparse.Namespace) -> None:
    setup_logging()  # the daemon is windowless when autostarted — logs must go to a file
    daemon = BrowserDaemon(args)
    idle = f"idle-shutdown={args.idle_shutdown_sec:.0f}s" if args.idle_shutdown_sec > 0 else "eternal"
    logger.info("warm browser daemon: chromium headless=%s proxy=%s %s",
                args.headless, "yes" if args.proxy else "no", idle)
    await daemon.start()

    runner = web.AppRunner(daemon.make_app())
    await runner.setup()
    site = web.TCPSite(runner, args.host, args.port)
    await site.start()
    logger.info("serving on http://%s:%d (POST /shutdown or Ctrl+C to stop)", args.host, args.port)
    try:
        await daemon._stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        logger.info("daemon stopping ...")
        await daemon.stop()
        await runner.cleanup()


def _parse_args() -> argparse.Namespace:
    from core.config import load_search_config

    cfg = load_search_config().browser
    p = argparse.ArgumentParser(description="Persistent warm stealth-browser daemon (chromium).")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=urlparse(cfg.daemon_url).port or 8765)
    p.add_argument("--no-headless", action="store_false", dest="headless")
    p.add_argument("--humanize", action="store_true", default=cfg.humanize)
    p.add_argument("--proxy", default=cfg.proxy or None)
    p.add_argument("--locale", default="en-US")
    p.add_argument("--max-requests", type=int, default=cfg.max_requests, dest="max_requests")
    p.add_argument("--max-age", type=float, default=cfg.max_age_sec, dest="max_age")
    p.add_argument("--max-rss-mb", type=int, default=cfg.max_rss_mb, dest="max_rss_mb")
    p.add_argument("--checkpoint-interval", type=float, default=cfg.checkpoint_interval,
                   dest="checkpoint_interval")
    p.add_argument("--nav-timeout", type=float, default=cfg.nav_timeout, dest="nav_timeout")
    p.add_argument("--wait", type=float, default=cfg.wait)
    p.add_argument("--idle-shutdown-sec", type=float, default=cfg.daemon_idle_shutdown_sec,
                   dest="idle_shutdown_sec", help="self-terminate after this idle time; 0 = eternal")
    p.set_defaults(headless=cfg.headless)
    return p.parse_args()


if __name__ == "__main__":
    from core.runtime import run_fast

    run_fast(_serve(_parse_args()))
