# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

# Crawl-ahead: after a search, warm the raw HTML of the top result URLs the model did
# NOT already get parsed content for, so a follow-up read_page on them is instant. Pages
# are cached under the SAME key read_page looks up, so the warm HTML is actually reused.
#
# Process discipline this is NOT fire-and-forget. Every
# warm-up is one tracked asyncio.Task held in a registry, bounded by a hard timeout and a
# concurrency semaphore, self-removing on completion, and cancellable via shutdown(). The
# legacy prefetch was fire-and-forget; this is the disciplined replacement.

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger("services.web_search")
trace_logger = logging.getLogger("trace.web_search")


# Manages tracked background warm-up tasks for result URLs.
class PrefetchManager:
    def __init__(self, *, max_concurrency: int = 3, per_url_timeout: float = 8.0,
                 task_timeout: float = 30.0) -> None:
        self._tasks: set[asyncio.Task] = set()
        self._sem = asyncio.Semaphore(max(1, max_concurrency))
        self._per_url_timeout = max(1.0, float(per_url_timeout))
        self._task_timeout = max(2.0, float(task_timeout))

    # Warm one URL's raw HTML into the page cache under read_page's cache key.
    async def _warm_one(self, url: str) -> bool:
        from core.cache import get_page_cache
        from core.fetch.antibot import is_antibot
        from core.fetch.url_utils import UnsafeFetchUrl, validate_public_fetch_url
        from core.read.service import _cache_key_for_read, _variant_label

        cache = get_page_cache()
        cache_key = _cache_key_for_read(url, variant=_variant_label(url))
        if cache.is_fresh(cache_key):
            return False
        try:
            import httpx

            safe_url = validate_public_fetch_url(url)
            async with self._sem:
                async with httpx.AsyncClient(
                    headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,*/*;q=0.8"},
                    timeout=self._per_url_timeout,
                    follow_redirects=True,
                ) as client:
                    resp = await client.get(safe_url)
            if resp.status_code >= 400:
                return False
            html = resp.text
            if not html or is_antibot(html):
                return False
            # Extract now (off the event loop) and warm the clean markdown, not raw HTML:
            # far smaller, FTS-searchable, and reused directly by a later read_page. A page
            # that doesn't extract to usable text is not worth warming (and not hoarded).
            from core.extract.page_normalizer import normalize_page

            md = await asyncio.get_running_loop().run_in_executor(
                None, normalize_page, safe_url, html
            )
            if not md or len(md.strip()) < 200:
                return False
            title = md.splitlines()[0].lstrip("# ").strip()[:200] if md.strip() else ""
            cache.cache_page(cache_key, title, clean_text=md, raw_html="")
            return True
        except UnsafeFetchUrl as exc:
            trace_logger.info("prefetch.blocked url=%r reason=%s", url, exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("prefetch fetch failed for %s: %s", url, exc)
        return False

    # Warm a batch of URLs under one hard-timeout-bounded task.
    async def _warm_batch(self, urls: list[str]) -> None:
        t0 = time.perf_counter()
        warmed = 0
        try:
            async with asyncio.timeout(self._task_timeout):
                results = await asyncio.gather(
                    *(self._warm_one(u) for u in urls), return_exceptions=True
                )
            warmed = sum(1 for r in results if r is True)
        except (TimeoutError, asyncio.CancelledError):
            pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("prefetch batch error: %s", exc)
        trace_logger.info(
            "prefetch.done urls=%d warmed=%d ms=%.0f", len(urls), warmed,
            (time.perf_counter() - t0) * 1000,
        )

    # Schedule a tracked warm-up task for the given URLs. Returns the task (or None).
    def schedule(self, urls: list[str]) -> asyncio.Task | None:
        targets = list(dict.fromkeys(u for u in urls if u))  # order-preserving dedup
        if not targets:
            return None
        task = asyncio.create_task(self._warm_batch(targets), name="prefetch")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    # Cancel and await all outstanding warm-up tasks (call at server shutdown).
    async def shutdown(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


_manager: PrefetchManager | None = None


# Return the lazily-initialised global PrefetchManager, configured from search_config.
def get_prefetch_manager() -> PrefetchManager:
    global _manager
    if _manager is None:
        from core.config import load_search_config

        cfg = load_search_config().search
        _manager = PrefetchManager(per_url_timeout=cfg.prefetch_fetch_timeout)
    return _manager


# Cancel all outstanding prefetch tasks (exposed for the MCP server's shutdown hook).
async def shutdown_prefetch() -> None:
    if _manager is not None:
        await _manager.shutdown()
