# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Deep onion search: per-site search over Tor → parallel scrape of top results → BM25-
compressed content returned directly (no bare-snippet SERP).

The onion mirror serves the same pages as the clearnet site, so a provider is just a search
path template + the generic article-link heuristic (developed/validated on the clearnet twin,
executed over the onion host at runtime). Search-page fetches and result-page scrapes both run
in parallel, each bounded by a per-link timeout so one slow Tor circuit can't stall the batch.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import quote_plus, urljoin, urlparse

from .registry import service_for
from .resolver import resolve_onion
from .transport import onion_fetch

logger = logging.getLogger("core.fetch.onion.search")

# Searchable providers: the onion serves the same search path as the clearnet site. Each
# path is validated on the clearnet twin before being enabled (paths rot / go SPA). DW is
# verified server-rendered; Guardian (/search now 404s) and RFE/RL (/s 403s) need their
# current search paths found before re-enabling — see TODO.
_SEARCH_PATHS: dict[str, str] = {
    "dw": "/search/?languageCode=en&item={q}",
}

# Path segments that mark a listing/nav page, not an article.
_LISTING_SEGMENTS = frozenset({
    "search", "s", "tag", "tags", "topic", "topics", "category", "categories",
    "latest", "live", "section", "sections", "author", "profile", "newsletter",
})
import re as _re

# A path is an article only with a strong marker — a date segment (/YYYY/…, most news), an
# article-id suffix (/a-12345678 on DW etc.), or a long numeric id. This rejects nav/section
# links (e.g. DW /en/top-stories/s-9097) that a bare href-sweep would otherwise grab.
_ARTICLE_RE = _re.compile(r"/(19|20)\d{2}/|/a-?\d{4,}\b|/\d{7,}\b")


@dataclass(slots=True)
class OnionResult:
    url: str
    host: str
    title: str
    content: str
    provider: str


# Heuristic: does this path look like an article (vs nav/listing)? Generic across news sites:
# at least two segments, not a known listing root, and a slug or a date segment.
def _is_article_path(path: str) -> bool:
    segs = [s for s in path.split("/") if s]
    if len(segs) < 2 or segs[0].lower() in _LISTING_SEGMENTS:
        return False
    return bool(_ARTICLE_RE.search(path))


# Extract candidate article URLs from a search-results page, rewritten to the onion host
# (relative links join the onion base; absolute clearnet-twin links get their host swapped).
def _extract_result_links(html: str, *, onion_base: str, clearnet_host: str, limit: int) -> list[str]:
    from bs4 import BeautifulSoup

    onion_host = urlparse(onion_base).netloc
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        raw = a["href"].strip()
        if not raw or raw.startswith(("#", "javascript:", "mailto:")):
            continue
        u = urljoin(onion_base, raw)
        parsed = urlparse(u)
        host = parsed.netloc.lower().removeprefix("www.")
        if host == clearnet_host:  # absolute clearnet link → point it at the onion mirror
            u = parsed._replace(netloc=onion_host).geturl()
            parsed = urlparse(u)
        if parsed.netloc != onion_host or not _is_article_path(parsed.path):
            continue
        key = u.split("#", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
        if len(out) >= limit:
            break
    return out


# Onion search root for a provider (its current onion host + the search path for `query`).
def _search_url(name: str, query: str) -> tuple[str, str, str] | None:
    svc = service_for(name)
    path_tmpl = _SEARCH_PATHS.get(name)
    if svc is None or not path_tmpl:
        return None
    onion = resolve_onion(svc)                       # current onion URL (cached/seeded)
    parsed = urlparse(onion)
    base = f"{parsed.scheme}://{parsed.netloc}"
    clearnet_host = urlparse(svc.clearnet_anchor).netloc.lower().removeprefix("www.")
    return base + path_tmpl.format(q=quote_plus(query)), base, clearnet_host


# Fetch one result page over Tor and return its BM25-compressed content (None on any failure).
async def _scrape_one(url: str, query: str, provider: str, *, timeout: float, max_chars: int):
    from core.extract.content_processor import compress_to_budget
    from core.extract.page_normalizer import normalize_page
    from core.fetch.antibot import is_antibot
    from core.fetch.thread_pool import io_pool as _io_pool

    try:
        r = await asyncio.wait_for(onion_fetch(url, timeout=timeout), timeout=timeout + 5)
    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
        return None
    if not r.ok or not r.text or is_antibot(r.text):
        return None
    loop = asyncio.get_running_loop()
    try:
        md = await asyncio.wait_for(
            loop.run_in_executor(_io_pool, lambda: normalize_page(url, r.text)), timeout=10
        )
    except Exception:  # noqa: BLE001
        return None
    if not md:
        return None
    content = compress_to_budget(md, query, max_chars)
    title = next((ln.lstrip("# ").strip() for ln in (content or md).splitlines() if ln.strip()), url)
    return OnionResult(url=url, host=urlparse(url).netloc, title=title[:200],
                       content=content, provider=provider)


# Deep onion search: locate via per-site search, then scrape+compress the top results — all
# in parallel, each bounded by per_link_timeout. Returns BM25-compressed content records.
async def onion_search(
    query: str, *, limit: int = 5, per_link_timeout: float = 20.0,
    max_chars: int = 4000, concurrency: int = 4, providers: tuple[str, ...] | None = None,
) -> list[OnionResult]:
    names = providers if providers is not None else tuple(_SEARCH_PATHS)
    # The search page is the gate and pays the cold-start cost (tor spawn + the first onion
    # descriptor lookup), so give it a more generous timeout than the article scrapes — a
    # tight per-link bound here would drop every result on a cold circuit.
    serp_timeout = max(per_link_timeout * 2.0, 45.0)

    # 1. Fetch each provider's search page in parallel; extract candidate article URLs.
    async def _serp(name: str) -> list[tuple[str, str]]:
        built = _search_url(name, query)
        if built is None:
            return []
        search_url, base, clearnet_host = built
        try:
            r = await asyncio.wait_for(onion_fetch(search_url, timeout=serp_timeout),
                                       timeout=serp_timeout + 5)
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            return []
        if not r.ok or not r.text:
            return []
        links = _extract_result_links(r.text, onion_base=base, clearnet_host=clearnet_host,
                                      limit=limit)
        return [(name, u) for u in links]

    serps = await asyncio.gather(*(_serp(n) for n in names), return_exceptions=True)
    candidates: list[tuple[str, str]] = []
    for s in serps:
        if isinstance(s, list):
            candidates.extend(s)
    # Interleave providers (round-robin) so one site can't dominate, then cap.
    candidates = _round_robin(candidates)[:limit]
    if not candidates:
        logger.info("onion_search: no candidates for %r", query[:120])
        return []

    # 2. Scrape + compress the candidates in parallel, bounded by a semaphore.
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _guarded(name: str, url: str):
        async with sem:
            return await _scrape_one(url, query, name, timeout=per_link_timeout, max_chars=max_chars)

    scraped = await asyncio.gather(*(_guarded(n, u) for n, u in candidates), return_exceptions=True)
    out = [r for r in scraped if isinstance(r, OnionResult)]
    logger.info("onion_search: %d/%d results for %r", len(out), len(candidates), query[:120])
    return out


# Round-robin interleave (name, url) pairs across providers for source diversity.
def _round_robin(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    by_name: dict[str, list[tuple[str, str]]] = {}
    for name, url in pairs:
        by_name.setdefault(name, []).append((name, url))
    out: list[tuple[str, str]] = []
    while any(by_name.values()):
        for name in list(by_name):
            if by_name[name]:
                out.append(by_name[name].pop(0))
    return out
