"""
engine_router.py — Telemetry-driven dispatcher replacing backend="auto".

This module owns only routing logic and statistics tracking.
Actual HTTP calls are handled by DDGSClient in ddgs_client.py,
which calls record() here after each search attempt.

Usage (from DDGSClient):
    router = get_router()
    engine = router.pick()
    # ... run search with that engine ...
    router.record(engine, Observation(...))

    # Or use pick_pool for parallel probing:
    engines = router.pick_pool(n=2)

    # Status display:
    router.status()  -> list[dict] sorted by score desc
"""

from __future__ import annotations

import hashlib
import logging
import random
import threading
import time
from typing import Optional

from core.fetch.engine_stats import ALL_ENGINES, HOSTED_ENGINES, EngineStats, Observation, make_registry

logger = logging.getLogger("core.fetch.engine_router")


# ---------------------------------------------------------------------------
# Per-engine parameter overrides
# ---------------------------------------------------------------------------

# Some DDGS backends need non-default params to work correctly.
# Keys map engine name → kwargs passed to ddgs.text() / DDGSClient.search_to_results().
ENGINE_REGION_OVERRIDE: dict[str, str] = {
    # region=wt-wt causes DDGS to build "wt.wikipedia.org" (non-existent).
    # Force English region so the URL resolves correctly.
    "wikipedia": "en-us",
}


# ---------------------------------------------------------------------------
# Cheap quality helpers (used by DDGSClient when recording observations)
# ---------------------------------------------------------------------------

def _quality_pass(results: list[dict]) -> bool:
    """True if >= 50% of results have a non-trivial snippet (>= 30 chars)."""
    if not results:
        return False
    good = sum(
        1 for r in results
        if len(r.get("body", "") or r.get("snippet", "")) >= 30
    )
    return good / len(results) >= 0.5


def _result_hash(results: list[dict]) -> int:
    """Stable hash of the top-5 URLs for stability tracking."""
    urls = "||".join(
        (r.get("href") or r.get("url") or "") for r in results[:5]
    )
    return int(hashlib.md5(urls.encode()).hexdigest()[:8], 16)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class EngineRouter:
    """
    Telemetry-driven dispatcher.  Thread-safe (uses a single Lock).

    All state lives in self.registry — a dict[engine_name, EngineStats].
    Tiers are recomputed from stats on every pick(); no caching needed
    since each EngineStats.score is a pure property over its window.
    """

    def __init__(
        self,
        registry: Optional[dict[str, EngineStats]] = None,
    ) -> None:
        self.registry: dict[str, EngineStats] = registry or make_registry()
        self._lock = threading.RLock()  # RLock: pick_pool() calls pick() while holding the lock

    # --- Tier views ---------------------------------------------------------

    def hot(self) -> list[EngineStats]:
        return [e for e in self.registry.values() if e.tier == "hot"]

    def warm(self) -> list[EngineStats]:
        return [e for e in self.registry.values() if e.tier == "warm"]

    def cold(self) -> list[EngineStats]:
        return [e for e in self.registry.values() if e.tier == "cold"]

    def tripped(self) -> list[EngineStats]:
        return [e for e in self.registry.values() if e.tier == "tripped"]

    # --- Pick logic ---------------------------------------------------------

    def pick(self) -> str:
        """
        Return the single best backend name.
        Prefers hot tier, falls back to warm, then cold.
        Within each tier: 90% highest-score, 10% random exploration.
        """
        with self._lock:
            candidates = self.hot() or self.warm() or self.cold()
            if not candidates:
                return "duckduckgo"
            if random.random() < 0.10:
                return random.choice(candidates).name
            return max(candidates, key=lambda e: e.score).name

    def pick_pool(self, n: int = 2) -> list[str]:
        """
        Return up to n backend names for parallel probing.
        Prefer hot engines, then warm, then cold to fill the pool.

        Cold-start matters because some callers run every query in a fresh
        subprocess, so the router has no telemetry yet. In that situation all
        engines start as "cold"; returning only one backend makes the search
        path unnecessarily fragile.
        """
        with self._lock:
            pool: list[str] = []
            hot = sorted(self.hot(), key=lambda e: e.score, reverse=True)
            warm = sorted(self.warm(), key=lambda e: e.score, reverse=True)
            cold = sorted(self.cold(), key=lambda e: e.score, reverse=True)
            for e in hot + warm + cold:
                if len(pool) >= n:
                    break
                pool.append(e.name)
            if not pool:
                pool = [self.pick()]
            return pool

    def available(self, exclude: set[str]) -> list[str]:
        """Return non-tripped engines not in the exclude set, sorted by score."""
        with self._lock:
            return [
                e.name
                for e in sorted(self.registry.values(), key=lambda e: e.score, reverse=True)
                if not e.is_tripped and e.name not in exclude
            ]

    # --- Telemetry recording ------------------------------------------------

    def record(self, engine: str, obs: Observation) -> None:
        """Record one observation for an engine. Thread-safe."""
        with self._lock:
            stats = self.registry.get(engine)
            if stats is not None:
                stats.record(obs)
                logger.debug(
                    "[%s] latency=%.2fs results=%d quality=%s tier=%s score=%.3f",
                    engine, obs.latency, obs.result_count,
                    obs.quality_pass, stats.tier, stats.score,
                )

    # --- Status report ------------------------------------------------------

    def status(self) -> list[dict]:
        """Sorted summary of all engines by score descending."""
        with self._lock:
            return sorted(
                [e.summary() for e in self.registry.values()],
                key=lambda d: d["score"],
                reverse=True,
            )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_router: Optional[EngineRouter] = None
_router_lock = threading.Lock()

def get_router() -> EngineRouter:
    """Return the lazily initialized global EngineRouter singleton.

    On first call, also registers hosted engines that have an API key configured.
    """
    global _router
    if _router is None:
        with _router_lock:
            if _router is None:
                try:
                    from core.fetch.hosted_clients import available_hosted_engines
                    hosted = available_hosted_engines()
                except Exception:
                    hosted = []
                registry = make_registry(extra_engines=hosted)
                _router = EngineRouter(registry)
                if hosted:
                    logger.info("EngineRouter: registered hosted engines: %s", hosted)
    return _router
