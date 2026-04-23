# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Smart Site Mapper module.

This module provides an agentic site mapper that performs BFS traversal of a domain,
pruning irrelevant branches using lexical scoring and densifying the results
using GliNER-based entity density analysis.

It is designed to return a 'map of the terrain' for deep research rather than
just a single-page parse.
"""

import asyncio
import logging
import re
import time
import urllib.parse
from collections import deque
from typing import TYPE_CHECKING, Any, Optional

import httpx
import trafilatura
from bs4 import BeautifulSoup

from core.cache.source_cache import canonicalize_url
from core.extract.scoring import densify_text_gliner as _densify_text_gliner, lexical_score as _lexical_score
from core.extract.semantic_dedup import minhash_dedup

if TYPE_CHECKING:
    from core.cache.source_cache import SourceCache

logger = logging.getLogger("core.mappers.site_mapper")

# ---------------------------------------------------------------------------
# URL canonicalization helpers
# ---------------------------------------------------------------------------

# Strip arxiv version suffixes: /abs/2304.11490v3 → /abs/2304.11490
_ARXIV_VERSION_RE = re.compile(r"(arxiv\.org/abs/[^/?#]+?)v\d+(/|$)", re.IGNORECASE)
# Query params that produce duplicate content on arxiv
_ARXIV_CONTEXT_PARAMS = frozenset({"context"})


def _canonical_link(url: str, base_domain: str) -> str:
    """Apply site-specific canonicalization on top of the generic normalizer."""
    url = canonicalize_url(url)
    if "arxiv.org" in base_domain:
        # Strip version suffixes
        url = _ARXIV_VERSION_RE.sub(r"\1\2", url)
        # Strip ?context= params
        p = urllib.parse.urlparse(url)
        if p.query:
            qs = urllib.parse.urlencode(
                [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if k not in _ARXIV_CONTEXT_PARAMS]
            )
            url = urllib.parse.urlunparse(p._replace(query=qs))
    return url


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ---------------------------------------------------------------------------
# SiteMapper
# ---------------------------------------------------------------------------

class SiteMapper:
    """Agentic BFS mapper with lexical pruning and GliNER densification."""

    def __init__(
        self,
        time_budget_sec: float = 30.0,
        concurrency: int = 5,
        max_nodes: int = 20,
        min_score: float = 0.15,
        cache: Optional["SourceCache"] = None,
        cache_ttl_sec: int = 86_400,
    ):
        self.time_budget = time_budget_sec
        self.concurrency = concurrency
        self.max_nodes = max_nodes
        self.min_score = min_score
        self._cache = cache
        self._cache_ttl = cache_ttl_sec

    async def map_domain(
        self,
        start_url: str,
        query_topic: str,
    ) -> dict[str, Any]:
        """Perform a smart crawl of the domain starting from start_url.

        Returns:
            dict: {
                "tree": {url: [links]},
                "nodes": {url: {"score": f, "snippet": s, "title": t}}
            }
        """
        logger.info("Starting Smart Map on %s (topic: %s)", start_url, query_topic)

        canonical_start = _canonical_link(start_url, urllib.parse.urlparse(start_url).netloc)
        queue: deque[str] = deque([canonical_start])
        visited: set[str] = {canonical_start}

        tree: dict[str, list[str]] = {}
        nodes: dict[str, dict[str, Any]] = {}

        deadline = time.time() + self.time_budget
        semaphore = asyncio.Semaphore(self.concurrency)

        parsed_base = urllib.parse.urlparse(start_url)
        base_domain = parsed_base.netloc

        # TODO: Keep current behavior for now, but switch this to verify=True
        # with a targeted TLS-failure fallback instead of disabling verification globally.
        async with httpx.AsyncClient(headers=HEADERS, verify=False, timeout=10.0) as client:

            async def process_url(url: str) -> None:
                if time.time() > deadline or len(nodes) >= self.max_nodes:
                    return

                async with semaphore:
                    html: str = ""
                    raw_text: str = ""
                    title: str = ""

                    # 1. Cache-first fetch
                    cached = self._cache.get_cached(url) if self._cache else None
                    if cached and cached.status == "ok" and self._cache and self._cache.is_fresh(url, self._cache_ttl):
                        html = cached.raw_html or ""
                        raw_text = cached.clean_text
                        title = cached.title
                        logger.debug("Cache hit: %s", url)
                    else:
                        try:
                            r = await client.get(url, follow_redirects=True)
                            if r.status_code != 200:
                                return
                            html = r.text
                        except Exception as exc:
                            logger.debug("Failed to fetch %s: %s", url, exc)
                            return

                        raw_text = trafilatura.extract(html) or ""
                        try:
                            soup = BeautifulSoup(html, "html.parser")
                            title = (soup.title.string if soup.title else "").strip()
                        except Exception:
                            title = ""

                        if self._cache and raw_text:
                            try:
                                self._cache.cache_page(url, title, raw_text, raw_html=html)
                            except Exception as exc:
                                logger.debug("Cache write failed for %s: %s", url, exc)

                    # 2. Scoring
                    lex_score = _lexical_score(query_topic, title, raw_text[:500], url)

                    # 3. Pruning
                    if lex_score < self.min_score and url != canonical_start:
                        logger.debug("Pruned %s (score: %.2f)", url, lex_score)
                        return

                    # 4. Densification (GliNER)
                    try:
                        densified_snippet = _densify_text_gliner(raw_text, output_chars=500)
                    except Exception:
                        densified_snippet = raw_text[:500]

                    densified_snippet = densified_snippet.replace("\n", " ").strip()

                    nodes[url] = {
                        "score": round(lex_score, 3),
                        "title": title,
                        "snippet": densified_snippet,
                    }

                    # 5. Link Discovery
                    links = self._extract_links(html, url, base_domain)
                    tree[url] = list(links)

                    for link in links:
                        if link not in visited:
                            visited.add(link)
                            queue.append(link)

            # BFS Loop
            while queue and time.time() < deadline and len(nodes) < self.max_nodes:
                batch: list[str] = []
                while queue and len(batch) < self.concurrency:
                    batch.append(queue.popleft())

                if not batch:
                    break

                await asyncio.gather(*(process_url(u) for u in batch))

        # MinHash dedup on collected nodes — catches content-identical pages
        # that survived URL canonicalization (e.g. mirrors, redirects).
        if len(nodes) > 1:
            node_list = list(nodes.items())
            deduped = minhash_dedup(
                node_list,
                text_fn=lambda item: item[1].get("snippet", ""),
                threshold=0.70,
            )
            if len(deduped) < len(node_list):
                logger.info(
                    "MinHash dedup: %d -> %d nodes",
                    len(node_list),
                    len(deduped),
                )
                nodes = dict(deduped)

        logger.info("Smart Map finished. Collected %d relevant nodes.", len(nodes))
        return {
            "tree": tree,
            "nodes": nodes,
        }

    def _extract_links(self, html: str, base_url: str, base_domain: str) -> set[str]:
        if not html:
            return set()
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return set()
        links: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            try:
                full_url = urllib.parse.urljoin(base_url, href).split("#")[0]
                parsed_url = urllib.parse.urlparse(full_url)
                if parsed_url.scheme in ("http", "https") and parsed_url.netloc == base_domain:
                    links.add(_canonical_link(full_url, base_domain))
            except Exception:
                continue
        return links
