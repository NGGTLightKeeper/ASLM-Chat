# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

# Short-horizon memory of what the model was just shown, so the search tool does not
# echo the same thing back within seconds. Two independent windows:
#
#   * repeat block — an IDENTICAL query (same normalized text + params) seen within
#     repeat_block_window is hard-blocked: no engines are hit, the caller gets a note
#     pointing back at the previous results.
#   * source suppression — a DIFFERENT but overlapping query has its already-shown
#     result URLs dropped within seen_source_window, so the model sees only what is new.
#
# Process-global and time-bounded (entries expire), so it needs no session id and the
# maps cannot grow without limit.

from __future__ import annotations

import threading
import time

from core.cache.query_normalizer import normalize_exact_query_key
from core.cache.source_cache import canonicalize_url


# In-memory recency tracker for queries and served source URLs.
class RecentSearchTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queries: dict[str, float] = {}   # exact query key -> last served ts
        self._sources: dict[str, float] = {}   # canonical url   -> last served ts

    # Composite identity of a query: normalized text + result-affecting params.
    @staticmethod
    def query_key(
        query: str,
        *,
        region: str = "",
        safesearch: str = "moderate",
        timelimit: str | None = None,
        effort: str = "low",
        shopping: bool = False,
        academic: bool = False,
    ) -> str:
        exact = normalize_exact_query_key(query)
        return (
            f"{exact}|{region}|{safesearch}|{timelimit or ''}|{effort}"
            f"|{int(bool(shopping))}|{int(bool(academic))}"
        )

    # Drop entries older than the larger of the two windows (cheap housekeeping).
    def _prune(self, now: float, horizon: float) -> None:
        cutoff = now - horizon
        if self._queries:
            self._queries = {k: t for k, t in self._queries.items() if t >= cutoff}
        if self._sources:
            self._sources = {k: t for k, t in self._sources.items() if t >= cutoff}

    # Seconds since this exact query was last served, or None if outside the window.
    def repeat_age(self, query_key: str, window: float) -> float | None:
        if window <= 0:
            return None
        now = time.time()
        with self._lock:
            ts = self._queries.get(query_key)
        if ts is None:
            return None
        age = now - ts
        return age if age <= window else None

    # Return the subset of urls served to the model within the suppression window.
    def recently_seen(self, urls: list[str], window: float) -> set[str]:
        if window <= 0 or not urls:
            return set()
        now = time.time()
        with self._lock:
            return {
                u for u in urls
                if (ts := self._sources.get(canonicalize_url(u))) is not None and (now - ts) <= window
            }

    # Record that this query and these source URLs were just served to the model.
    def record(self, query_key: str, urls: list[str], *, horizon: float = 60.0) -> None:
        now = time.time()
        with self._lock:
            self._queries[query_key] = now
            for u in urls:
                if u:
                    self._sources[canonicalize_url(u)] = now
            self._prune(now, horizon)


_tracker: RecentSearchTracker | None = None


# Return the lazily-initialised global tracker.
def get_recent_tracker() -> RecentSearchTracker:
    global _tracker
    if _tracker is None:
        _tracker = RecentSearchTracker()
    return _tracker
