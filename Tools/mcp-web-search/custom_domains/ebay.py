# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.fetch.camoufox_fetcher import fetch_with_camoufox, is_camoufox_available

from custom_domains.common import CHROME_BASIC_HEADERS, extract_with_preferred_pipeline, looks_blocked, trim


# Fetch eBay listing via Camoufox, then Patchright fallback; return extraction snapshot dict.
async def fetch_ebay_snapshot(url: str, timeout: float = 20.0, wait: float = 4.0) -> dict[str, Any]:
    started = time.perf_counter()
    candidates: list[dict[str, Any]] = []
    attempts_per_engine = 2

    if is_camoufox_available():
        for attempt in range(1, attempts_per_engine + 1):
            result = await fetch_with_camoufox(
                url,
                timeout_sec=timeout,
                process_timeout=timeout + 20.0,
                wait_sec=wait,
                warmup_count=0,
                normalize=False,
            )
            html = result.html or ""
            title = trim(result.title, 180)
            blocked = looks_blocked(title, html)
            if html and not blocked:
                parsed = extract_with_preferred_pipeline(url, html, prefer_trafilatura=True)
                candidates.append(
                    {
                        "source": "ebay",
                        "url": url,
                        "engine": "camoufox",
                        "attempt": attempt,
                        "status": 200 if result.success else 0,
                        "final_url": result.url or url,
                        "content_type": "",
                        "title": title,
                        "raw_html_chars": len(html),
                        "blocked_like": blocked,
                        **parsed,
                    }
                )
                break

    if candidates:
        best = max(candidates, key=lambda item: (int(item["markdown_chars"]), int(item["raw_html_chars"])))
        best["duration_sec"] = round(time.perf_counter() - started, 3)
        return best

    from patchright.async_api import async_playwright

    for attempt in range(1, attempts_per_engine + 1):
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=CHROME_BASIC_HEADERS["User-Agent"])
            page = await context.new_page()
            response = await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
            await page.wait_for_timeout(int(wait * 1000))
            html = await page.content()
            final_url = page.url
            title = trim(await page.title(), 180)
            status = response.status if response else 0
            content_type = ""
            if response:
                try:
                    content_type = response.headers.get("content-type", "")
                except Exception:
                    content_type = ""
            await context.close()
            await browser.close()

        blocked = looks_blocked(title, html)
        if html and not blocked:
            parsed = extract_with_preferred_pipeline(url, html, prefer_trafilatura=True)
            candidates.append(
                {
                    "source": "ebay",
                    "url": url,
                    "engine": "patchright",
                    "attempt": attempt,
                    "status": int(status or 0),
                    "final_url": final_url,
                    "content_type": content_type,
                    "title": title,
                    "raw_html_chars": len(html),
                    "blocked_like": blocked,
                    **parsed,
                }
            )
            break

    return {
        "source": "ebay",
        "url": url,
        "engine": "none",
        "status": 0,
        "final_url": url,
        "content_type": "",
        "title": "",
        "raw_html_chars": 0,
        "blocked_like": True,
        "duration_sec": round(time.perf_counter() - started, 3),
        "strategy": "none",
        "markdown": "",
        "markdown_chars": 0,
        "markdown_preview": "",
    }


# CLI argument parser for standalone ebay.py runs.
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the custom eBay snapshot fetcher.")
    parser.add_argument("url")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--wait", type=float, default=4.0)
    return parser.parse_args()


# CLI entry: fetch snapshot and print JSON to stdout.
def main() -> None:
    args = _parse_args()
    result = asyncio.run(fetch_ebay_snapshot(args.url, timeout=args.timeout, wait=args.wait))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


from urllib.parse import urlparse

from custom_domains.base import FetchContext, PageResult

_EBAY_HOSTS = frozenset({
    "ebay.com", "ebay.co.uk", "ebay.de", "ebay.fr", "ebay.it",
})


# Unified handler: fetch an eBay listing snapshot (Camoufox → Patchright).
class EbayHandler:
    name = "ebay"
    fallback_to_generic = True
    scope = "read_page"  # retail page is heavy/antibot; snippet-only in web_search

    # True for known eBay marketplace hosts.
    def matches(self, url: str) -> bool:
        host = urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")
        return host in _EBAY_HOSTS

    # Fetch a snapshot; empty/blocked results defer to read_page's generic pipeline.
    async def read(self, url: str, ctx: FetchContext) -> PageResult:
        try:
            snapshot = await fetch_ebay_snapshot(url, timeout=ctx.timeout)
        except Exception:
            return PageResult(ok=False, method="ebay_custom", error="ebay snapshot failed")
        markdown = str(snapshot.get("markdown") or "").strip()
        blocked = bool(snapshot.get("blocked_like"))
        ok = bool(markdown) and not blocked
        return PageResult(
            markdown=markdown,
            ok=ok,
            method=str(snapshot.get("engine") or "ebay_custom"),
            blocked=blocked,
        )


HANDLER = EbayHandler()
