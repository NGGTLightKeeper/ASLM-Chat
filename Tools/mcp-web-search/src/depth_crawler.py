# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Selective depth crawler: Scrapy CrawlSpider for following internal links
1-2 levels deep on chosen domains.  Results go into SourceCache.

Architecture: runs Scrapy in a child subprocess via asyncio.create_subprocess_exec
so Twisted's reactor is fully isolated — no ReactorNotRestartable errors,
and the main asyncio loop is never blocked.

Public API
----------
schedule_crawl(cache, seed_urls, allowed_domains, ...)  -- async, non-blocking
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .source_cache import SourceCache

logger = logging.getLogger("depth_crawler")

# ---------------------------------------------------------------------------
# Scrapy worker script (written to a temp file and executed as subprocess).
# ---------------------------------------------------------------------------

_WORKER_SCRIPT = r"""
import sys, json, os, re, html as html_lib
from urllib.parse import urlparse

params = json.loads(sys.argv[1])
seed_urls      = params["seed_urls"]
allowed_domains = params["allowed_domains"]
depth_limit    = params["depth_limit"]
max_pages      = params["max_pages"]
autothrottle   = params["autothrottle_target"]
db_path        = params["db_path"]
default_ttl    = params["default_ttl"]
src_path       = params["src_path"]
store_raw_html = params.get("store_raw_html", False)

if src_path not in sys.path:
    sys.path.insert(0, src_path)

try:
    from source_cache import SourceCache
    from page_normalizer import normalize_page as _normalize
except ImportError:
    _normalize = None
    from source_cache import SourceCache

cache = SourceCache(db_path=db_path, default_ttl=default_ttl)

try:
    import scrapy
    from scrapy.crawler import CrawlerProcess
    from scrapy.linkextractors import LinkExtractor
    from scrapy.spiders import Spider
except ImportError:
    print("scrapy not installed", file=sys.stderr)
    sys.exit(0)

_link_extractor = LinkExtractor(allow_domains=allowed_domains)

def _store_page(response):
    # Extract, normalize, and cache a response.
    if response.status != 200:
        return
    raw_html = response.text or ""
    if len(raw_html) < 100:
        return
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    if m:
        title = html_lib.unescape(m.group(1)).strip()[:500]
    if _normalize is not None:
        clean_text = _normalize(response.url, raw_html, "")
    else:
        clean_text = re.sub(r"<[^>]+>", " ", raw_html)
        clean_text = re.sub(r"\s{2,}", "\n", clean_text).strip()
    if not clean_text or len(clean_text) < 50:
        return
    cache.cache_page(
        url=response.url,
        title=title,
        clean_text=clean_text,
        raw_html=raw_html if store_raw_html else "",
        domain=urlparse(response.url).netloc.lower(),
        status="ok",
    )

class SourceSpider(Spider):
    name = "source_spider"
    allowed_domains = list(allowed_domains)
    start_urls = list(seed_urls)

    def parse(self, response):
        _store_page(response)
        # Follow links within allowed domains up to depth_limit.
        for link in _link_extractor.extract_links(response):
            yield scrapy.Request(link.url, callback=self.parse)

settings = {
    "DEPTH_LIMIT": depth_limit,
    "CLOSESPIDER_PAGECOUNT": max_pages,
    "AUTOTHROTTLE_ENABLED": True,
    "AUTOTHROTTLE_TARGET_CONCURRENCY": autothrottle,
    "AUTOTHROTTLE_START_DELAY": 1.0,
    "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
    "CONCURRENT_REQUESTS": 4,
    "DOWNLOAD_DELAY": 1.0,
    "ROBOTSTXT_OBEY": True,
    "LOG_LEVEL": "WARNING",
    "LOG_ENABLED": True,
    "TELNETCONSOLE_ENABLED": False,
    "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
    "RETRY_TIMES": 1,
    "DOWNLOAD_TIMEOUT": 15,
}

process = CrawlerProcess(settings=settings, install_root_handler=False)
process.crawl(SourceSpider)
process.start(stop_after_crawl=True)
"""


# ---------------------------------------------------------------------------
# Public async entry point.
# ---------------------------------------------------------------------------

async def schedule_crawl(
    cache: SourceCache,
    seed_urls: list[str],
    allowed_domains: list[str],
    depth_limit: int = 1,
    max_pages: int = 20,
    autothrottle_target: float = 2.0,
    timeout: float = 300.0,
    store_raw_html: bool = False,
) -> None:
    """Run a Scrapy depth crawl in a child subprocess.

    Non-blocking from the caller's perspective — awaited but runs in a
    separate Python process so Twisted's reactor is fully isolated.
    """
    if not seed_urls or not allowed_domains:
        return

    depth_limit = min(max(depth_limit, 1), 2)
    max_pages = min(max(max_pages, 1), 100)

    src_path = str(Path(__file__).resolve().parent)

    params = json.dumps({
        "seed_urls": seed_urls,
        "allowed_domains": allowed_domains,
        "depth_limit": depth_limit,
        "max_pages": max_pages,
        "autothrottle_target": autothrottle_target,
        "db_path": cache._db_path,
        "default_ttl": cache._default_ttl,
        "src_path": src_path,
        "store_raw_html": store_raw_html,
    })

    # Write worker script to a temp file.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(_WORKER_SCRIPT)
        worker_path = f.name

    logger.info(
        "depth crawl: %d seeds, domains=%s, depth=%d, max_pages=%d",
        len(seed_urls), allowed_domains, depth_limit, max_pages,
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, worker_path, params,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            logger.warning("depth crawl timed out after %.0fs", timeout)
            return

        if proc.returncode != 0 and stderr:
            err = stderr.decode(errors="replace").strip()
            logger.warning("depth crawl subprocess error: %s", err[:500])
        else:
            logger.info("depth crawl finished (exit %d)", proc.returncode)
    except Exception as e:
        logger.warning("depth crawl failed: %s", e)
    finally:
        try:
            os.unlink(worker_path)
        except OSError:
            pass
