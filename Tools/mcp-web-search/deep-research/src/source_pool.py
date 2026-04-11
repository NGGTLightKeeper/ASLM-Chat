# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Unified source pool for the deep-research pipeline.

Collects extracted sources from all stages (first pass, iterations, swarm)
into a single deduplicated pool.  Replaces the scattered set-tracking
(all_processed_urls, all_content_hashes) with one coherent data structure.
"""

from __future__ import annotations

import logging
from typing import List, Set
from urllib.parse import urlparse

from .models import ExtractedSource, SearchResult

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    """Normalize a URL for dedup comparison (lowercase host, strip trailing slash)."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        path = parsed.path.rstrip("/") or "/"
        return f"{parsed.scheme}://{host}{path}"
    except Exception:
        return url.lower().strip()


class SourcePool:
    """Deduplicated collection of extracted sources across all pipeline stages."""

    def __init__(self):
        self._sources: list[ExtractedSource] = []
        self._seen_urls: set[str] = set()
        self._seen_hashes: set[str] = set()
        self._raw_urls: set[str] = set()

    def add(self, source: ExtractedSource) -> bool:
        """Add a source if not a duplicate.  Returns True if added."""
        norm_url = _normalize_url(source.url)
        if norm_url in self._seen_urls:
            return False
        if source.content_hash and source.content_hash in self._seen_hashes:
            return False
        self._seen_urls.add(norm_url)
        if source.content_hash:
            self._seen_hashes.add(source.content_hash)
        self._sources.append(source)
        return True

    def add_many(self, sources: List[ExtractedSource]) -> int:
        """Bulk add sources.  Returns count of newly added items."""
        return sum(1 for s in sources if self.add(s))

    def merge_raw_results(self, results: List[SearchResult]) -> None:
        """Track URLs from raw search results for early dedup before extraction."""
        for r in results:
            self._raw_urls.add(_normalize_url(r.url))

    def is_known_url(self, url: str) -> bool:
        """Check if a URL is already tracked (extracted or from raw results)."""
        norm = _normalize_url(url)
        return norm in self._seen_urls or norm in self._raw_urls

    @property
    def sources(self) -> List[ExtractedSource]:
        """Return all deduplicated extracted sources."""
        return list(self._sources)

    @property
    def urls(self) -> Set[str]:
        """Return the set of normalized URLs of extracted sources."""
        return set(self._seen_urls)

    @property
    def content_hashes(self) -> Set[str]:
        """Return the set of content hashes."""
        return set(self._seen_hashes)

    @property
    def raw_urls(self) -> Set[str]:
        """Return the set of raw result URLs tracked before extraction."""
        return set(self._raw_urls)

    def __len__(self) -> int:
        return len(self._sources)

    def __bool__(self) -> bool:
        return bool(self._sources)
