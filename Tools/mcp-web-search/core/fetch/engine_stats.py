"""
engine_stats.py — Rolling reputation tracker for DDGS backends.

Each EngineStats instance stores the last N observations for one backend.
Scoring formula:
    score = 0.35 * (1 - norm_latency)
          + 0.25 * success_rate
          + 0.20 * quality_pass_rate
          + 0.10 * freshness_score
          + 0.10 * result_stability

Tiers:
    hot      — score >= 0.65 and not tripped
    warm     — 0.35 <= score < 0.65 and not tripped
    cold     — score < 0.35 and not tripped
    tripped  — circuit breaker active (cooldown_until > now)
"""

from __future__ import annotations

import math
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW = 30             # rolling observations per engine
COOLDOWN_SECONDS = 600  # 10 min circuit-breaker cooldown
TRIP_THRESHOLD = 0.6    # error_rate above this triggers the breaker

# Latency reference point for normalization: 99th-percentile expected worst case
LATENCY_CEIL = 8.0      # seconds — anything above this scores 0 on latency


# ---------------------------------------------------------------------------
# One observation
# ---------------------------------------------------------------------------

@dataclass
class Observation:
    ts: float           # unix timestamp of the call
    latency: float      # wall-clock seconds from request to first result
    success: bool       # True if we got >= 1 result back
    result_count: int   # how many results were returned
    quality_pass: bool  # passed cheap quality check (non-empty snippets etc.)
    result_hash: int    # hash of top-5 URLs for stability check


# ---------------------------------------------------------------------------
# Per-engine rolling stats
# ---------------------------------------------------------------------------

@dataclass
class EngineStats:
    name: str
    window: Deque[Observation] = field(default_factory=lambda: deque(maxlen=WINDOW))
    cooldown_until: float = 0.0
    consecutive_errors: int = 0

    # --- Derived metrics ---------------------------------------------------

    @property
    def is_tripped(self) -> bool:
        return time.time() < self.cooldown_until

    @property
    def observation_count(self) -> int:
        return len(self.window)

    @property
    def latencies(self) -> list[float]:
        return [o.latency for o in self.window if o.success]

    @property
    def p50_latency(self) -> float:
        lats = self.latencies
        return statistics.median(lats) if lats else float("inf")

    @property
    def p95_latency(self) -> float:
        lats = sorted(self.latencies)
        if not lats:
            return float("inf")
        idx = max(0, math.ceil(0.95 * len(lats)) - 1)
        return lats[idx]

    @property
    def success_rate(self) -> float:
        if not self.window:
            return 0.5  # unknown → neutral prior
        return sum(1 for o in self.window if o.success) / len(self.window)

    @property
    def error_rate(self) -> float:
        return 1.0 - self.success_rate

    @property
    def quality_pass_rate(self) -> float:
        passed = [o for o in self.window if o.success]
        if not passed:
            return 0.5
        return sum(1 for o in passed if o.quality_pass) / len(passed)

    @property
    def freshness_score(self) -> float:
        """How recently did we see a success? 1.0 = <1 min ago, 0.0 = >30 min ago."""
        successes = [o for o in self.window if o.success]
        if not successes:
            return 0.0
        last = max(o.ts for o in successes)
        age = time.time() - last
        return max(0.0, 1.0 - age / 1800.0)

    @property
    def result_stability(self) -> float:
        """Fraction of consecutive result pairs that share the same hash."""
        hashes = [o.result_hash for o in self.window if o.success]
        if len(hashes) < 2:
            return 1.0
        matches = sum(1 for a, b in zip(hashes, hashes[1:]) if a == b)
        return matches / (len(hashes) - 1)

    @property
    def normalized_latency(self) -> float:
        """0 = instant, 1 = LATENCY_CEIL or worse."""
        return min(1.0, self.p50_latency / LATENCY_CEIL)

    @property
    def score(self) -> float:
        if self.is_tripped:
            return 0.0
        return (
            0.35 * (1.0 - self.normalized_latency)
            + 0.25 * self.success_rate
            + 0.20 * self.quality_pass_rate
            + 0.10 * self.freshness_score
            + 0.10 * self.result_stability
        )

    @property
    def tier(self) -> str:
        if self.is_tripped:
            return "tripped"
        s = self.score
        if s >= 0.65:
            return "hot"
        if s >= 0.35:
            return "warm"
        return "cold"

    # --- Mutation ----------------------------------------------------------

    def record(self, obs: Observation) -> None:
        self.window.append(obs)
        if obs.success:
            self.consecutive_errors = 0
        else:
            self.consecutive_errors += 1
            # trip circuit breaker on 3 consecutive errors or high error_rate in window
            if self.consecutive_errors >= 3 or (
                len(self.window) >= 5 and self.error_rate > TRIP_THRESHOLD
            ):
                self.cooldown_until = time.time() + COOLDOWN_SECONDS
                self.consecutive_errors = 0

    # --- Display -----------------------------------------------------------

    def summary(self) -> dict:
        return {
            "engine": self.name,
            "tier": self.tier,
            "score": round(self.score, 3),
            "observations": self.observation_count,
            "p50_lat": round(self.p50_latency, 2) if self.latencies else None,
            "p95_lat": round(self.p95_latency, 2) if self.latencies else None,
            "success_rate": round(self.success_rate, 3),
            "quality_pass_rate": round(self.quality_pass_rate, 3),
            "freshness": round(self.freshness_score, 3),
            "stability": round(self.result_stability, 3),
            "tripped_until": (
                time.strftime("%H:%M:%S", time.localtime(self.cooldown_until))
                if self.is_tripped else None
            ),
        }


# ---------------------------------------------------------------------------
# Registry of all active engines
# ---------------------------------------------------------------------------

# Engines confirmed working via stress-bench (2026-04-06, region=wt-wt).
# DDGS v9 available backends: brave, duckduckgo, google, grokipedia, mojeek,
#                             wikipedia, yahoo, yandex  (bing dropped in v9)
# Excluded: yandex (endpoint issues), brave/mojeek (frequent 4xx blocks),
#           grokipedia (experimental, low coverage).
ALL_ENGINES = [
    "duckduckgo",
    "google",
    "yahoo",
    "wikipedia",
]

# API-key-based hosted search providers.
# Only engines whose key is present in api_keys.json are registered in the router.
HOSTED_ENGINES = [
    "tavily",
    "brave",
    "bing",
    "serpapi",
]


def make_registry(extra_engines: list[str] | None = None) -> dict[str, EngineStats]:
    """Build the engine stats registry.

    Always includes ALL_ENGINES (DDGS backends).
    Pass *extra_engines* (e.g. available hosted providers) to add them too.
    """
    names = list(ALL_ENGINES)
    for name in (extra_engines or []):
        if name not in names:
            names.append(name)
    return {name: EngineStats(name=name) for name in names}
