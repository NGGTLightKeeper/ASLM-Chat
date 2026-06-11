# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import hashlib
import logging
import random
import threading
from typing import Optional

from core.fetch.engine_stats import (
    BACKUP_ENGINES,
    PRIMARY_ENGINES,
    EngineStats,
    Observation,
    make_registry,
)

logger = logging.getLogger("core.fetch.engine_router")

ENGINE_REGION_OVERRIDE: dict[str, str] = {}


# True if >= 50% of results have a non-trivial snippet (>= 30 chars).
def _quality_pass(results: list[dict]) -> bool:
    if not results:
        return False
    good = sum(
        1 for r in results
        if len(r.get("body", "") or r.get("snippet", "")) >= 30
    )
    return good / len(results) >= 0.5


# Stable hash of the top-5 URLs for stability tracking.
def _result_hash(results: list[dict]) -> int:
    urls = "||".join(
        (r.get("href") or r.get("url") or "") for r in results[:5]
    )
    return int(hashlib.md5(urls.encode()).hexdigest()[:8], 16)


# Telemetry-driven dispatcher; thread-safe via RLock.
class EngineRouter:

    # Wire registry and reentrant lock for nested pick_pool calls.
    def __init__(
        self,
        registry: Optional[dict[str, EngineStats]] = None,
    ) -> None:
        self.registry: dict[str, EngineStats] = registry or make_registry()
        self._lock = threading.RLock()

    # Engines currently in the hot tier.
    def hot(self) -> list[EngineStats]:
        return [e for e in self.registry.values() if e.tier == "hot"]

    # Engines currently in the warm tier.
    def warm(self) -> list[EngineStats]:
        return [e for e in self.registry.values() if e.tier == "warm"]

    # Engines currently in the cold tier.
    def cold(self) -> list[EngineStats]:
        return [e for e in self.registry.values() if e.tier == "cold"]

    # Engines with an active circuit-breaker trip.
    def tripped(self) -> list[EngineStats]:
        return [e for e in self.registry.values() if e.tier == "tripped"]

    # Return the single best backend name (hot → warm → cold; 10% exploration).
    def pick(self) -> str:
        with self._lock:
            primary_names = set(PRIMARY_ENGINES)
            candidates = [engine for engine in self.hot() if engine.name in primary_names]
            candidates = candidates or [engine for engine in self.warm() if engine.name in primary_names]
            candidates = candidates or [engine for engine in self.cold() if engine.name in primary_names]
            if not candidates:
                return "duckduckgo"
            if random.random() < 0.10:
                return random.choice(candidates).name
            return max(candidates, key=lambda e: e.score).name

    # Return up to n backend names for parallel probing (hot, then warm, then cold).
    def pick_pool(self, n: int = 2) -> list[str]:
        with self._lock:
            return self._ranked_pool(PRIMARY_ENGINES, n)

    # Return backup engines in reputation order; never mix them into primaries.
    def pick_backup_pool(self, n: int = len(BACKUP_ENGINES)) -> list[str]:
        with self._lock:
            return self._ranked_pool(BACKUP_ENGINES, n)

    def _ranked_pool(self, names: list[str], n: int) -> list[str]:
        candidates = [
            self.registry[name]
            for name in names
            if name in self.registry and not self.registry[name].is_tripped
        ]
        ranked = sorted(candidates, key=lambda e: (e.tier != "hot", e.tier == "cold", -e.score))
        return [engine.name for engine in ranked[: max(1, n)]]

    # Return non-tripped engines not in exclude, sorted by score.
    def available(self, exclude: set[str]) -> list[str]:
        with self._lock:
            return [
                e.name
                for e in sorted(self.registry.values(), key=lambda e: e.score, reverse=True)
                if not e.is_tripped and e.name not in exclude
            ]

    # Record one observation and update engine reputation.
    def record(self, engine: str, obs: Observation) -> None:
        with self._lock:
            stats = self.registry.get(engine)
            if stats is not None:
                stats.record(obs)
                logger.debug(
                    "[%s] latency=%.2fs results=%d quality=%s tier=%s score=%.3f",
                    engine, obs.latency, obs.result_count,
                    obs.quality_pass, stats.tier, stats.score,
                )

    # Per-engine summary rows sorted by score (for status endpoints).
    def status(self) -> list[dict]:
        with self._lock:
            return sorted(
                [e.summary() for e in self.registry.values()],
                key=lambda d: d["score"],
                reverse=True,
            )


_router: Optional[EngineRouter] = None
_router_lock = threading.Lock()


# Lazily initialized global EngineRouter; registers hosted engines on first call.
def get_router() -> EngineRouter:
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
