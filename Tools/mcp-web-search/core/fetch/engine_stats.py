# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import math
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

# Rolling window size per engine.
WINDOW = 30
# Circuit-breaker cooldown after repeated failures (seconds).
COOLDOWN_SECONDS = 600
# Error rate above this trips the breaker.
TRIP_THRESHOLD = 0.6
# Latency normalization ceiling: above this scores zero on latency.
LATENCY_CEIL = 8.0


# One completed search call sample for reputation scoring.
@dataclass
class Observation:
    ts: float           # unix timestamp of the call
    latency: float      # wall-clock seconds from request to first result
    success: bool       # True if we got >= 1 result back
    result_count: int   # how many results were returned
    quality_pass: bool  # passed cheap quality check (non-empty snippets etc.)
    result_hash: int    # hash of top-5 URLs for stability check


# Rolling reputation tracker for one DDGS or hosted backend.
@dataclass
class EngineStats:
    name: str
    window: Deque[Observation] = field(default_factory=lambda: deque(maxlen=WINDOW))
    cooldown_until: float = 0.0
    consecutive_errors: int = 0

    # True while circuit-breaker cooldown is active.
    @property
    def is_tripped(self) -> bool:
        return time.time() < self.cooldown_until

    # Number of observations in the rolling window.
    @property
    def observation_count(self) -> int:
        return len(self.window)

    # Latencies from successful observations only.
    @property
    def latencies(self) -> list[float]:
        return [o.latency for o in self.window if o.success]

    # Median latency of successful calls.
    @property
    def p50_latency(self) -> float:
        lats = self.latencies
        return statistics.median(lats) if lats else float("inf")

    # 95th-percentile latency of successful calls.
    @property
    def p95_latency(self) -> float:
        lats = sorted(self.latencies)
        if not lats:
            return float("inf")
        idx = max(0, math.ceil(0.95 * len(lats)) - 1)
        return lats[idx]

    # Fraction of window observations that returned results.
    @property
    def success_rate(self) -> float:
        if not self.window:
            return 0.5  # unknown → neutral prior
        return sum(1 for o in self.window if o.success) / len(self.window)

    # Complement of success_rate.
    @property
    def error_rate(self) -> float:
        return 1.0 - self.success_rate

    # Fraction of successful calls that passed the quality check.
    @property
    def quality_pass_rate(self) -> float:
        passed = [o for o in self.window if o.success]
        if not passed:
            return 0.5
        return sum(1 for o in passed if o.quality_pass) / len(passed)

    # Decay from 1.0 (recent success) to 0.0 over 30 minutes since last success.
    @property
    def freshness_score(self) -> float:
        successes = [o for o in self.window if o.success]
        if not successes:
            return 0.0
        last = max(o.ts for o in successes)
        age = time.time() - last
        return max(0.0, 1.0 - age / 1800.0)

    # Fraction of consecutive successful pairs sharing the same result hash.
    @property
    def result_stability(self) -> float:
        hashes = [o.result_hash for o in self.window if o.success]
        if len(hashes) < 2:
            return 1.0
        matches = sum(1 for a, b in zip(hashes, hashes[1:]) if a == b)
        return matches / (len(hashes) - 1)

    # Normalized latency: 0 = instant, 1 = LATENCY_CEIL or worse.
    @property
    def normalized_latency(self) -> float:
        return min(1.0, self.p50_latency / LATENCY_CEIL)

    # Weighted composite reputation score (0 when tripped).
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

    # hot / warm / cold / tripped label from score and breaker state.
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

    # Append observation and trip breaker on sustained failures.
    def record(self, obs: Observation) -> None:
        self.window.append(obs)
        if obs.success:
            self.consecutive_errors = 0
        else:
            self.consecutive_errors += 1
            # Trip circuit breaker on 3 consecutive errors or high error_rate in window.
            if self.consecutive_errors >= 3 or (
                len(self.window) >= 5 and self.error_rate > TRIP_THRESHOLD
            ):
                self.cooldown_until = time.time() + COOLDOWN_SECONDS
                self.consecutive_errors = 0

    # JSON-serializable status dict for debugging and dashboards.
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


# DDGS primary backends. Backups are only used after a primary miss/failure.
PRIMARY_ENGINES = [
    "duckduckgo",
    "google",
    "yahoo",
]

BACKUP_ENGINES = [
    "startpage",
    "mojeek",
    "brave",
    "yandex",
    "qwant",
    "yep",
    "stackoverflow",
]

ALL_ENGINES = [*PRIMARY_ENGINES, *BACKUP_ENGINES]

# API-key hosted providers; only engines with keys in api_keys.json are registered.
HOSTED_ENGINES = [
    "tavily",
    "brave",
    "serpapi",
]


# Build engine stats registry; optional extra_engines adds hosted providers.
def make_registry(extra_engines: list[str] | None = None) -> dict[str, EngineStats]:
    names = list(ALL_ENGINES)
    for name in (extra_engines or []):
        if name not in names:
            names.append(name)
    return {name: EngineStats(name=name) for name in names}
