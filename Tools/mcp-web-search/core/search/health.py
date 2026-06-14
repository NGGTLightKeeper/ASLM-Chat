# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Per-engine health tracking with a circuit breaker.

States follow the classic breaker: CLOSED (healthy) → OPEN (cooling down) →
HALF_OPEN (one probe allowed) → CLOSED on success or back to OPEN with
exponential backoff on failure.

Two trigger classes with different cooldowns:
- error (HTTP 4xx/5xx block, timeout, BLOCKED/CHANGED parse): long cooldown;
- degradation (success but thin results or latency spike): short cooldown.

The tracker is in-memory and per-process. EWMA latency uses a fixed alpha —
cheap and good enough to spot a p95-style spike without storing samples.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum

# Cooldowns (seconds). Config-level constants by design — tune here, not inline.
DEGRADATION_COOLDOWN = 30.0
ERROR_COOLDOWN = 300.0
# Backoff multiplier applied when a half-open probe fails again, and its cap.
BACKOFF_FACTOR = 2.0
MAX_COOLDOWN = 1800.0
# A half-open probe is admitted but its outcome (record()) can be lost — e.g. the
# search deadline cancels the producer before the engine's status event is consumed.
# An in-flight probe older than this is treated as abandoned and a fresh one is
# admitted, so a single lost outcome cannot lock the engine out for the process life.
PROBE_TIMEOUT = 60.0

# EWMA smoothing for fetch latency.
_EWMA_ALPHA = 0.30
# A successful call this much slower than the engine's EWMA counts as degradation.
_LATENCY_SPIKE_FACTOR = 3.0
# Successful parses with fewer results than this count as degradation.
_THIN_RESULTS_FLOOR = 1

# Parse statuses that count as hard errors for the breaker.
_ERROR_STATUSES = frozenset({"blocked", "timeout", "error", "changed"})


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(slots=True)
class EngineHealth:
    state: BreakerState = BreakerState.CLOSED
    open_until: float = 0.0
    cooldown: float = 0.0  # current cooldown (grows with backoff)
    ewma_fetch_ms: float = 0.0
    successes: int = 0
    errors: int = 0
    degradations: int = 0
    last_status: str = ""
    # True while a half-open probe is in flight (only one probe at a time).
    probe_inflight: bool = field(default=False, repr=False)
    # When the in-flight probe was admitted, so an abandoned probe can be expired.
    probe_started: float = field(default=0.0, repr=False)


# In-memory health registry + circuit breaker for SERP engines.
class EngineHealthTracker:

    # clock is injectable for tests.
    def __init__(self, *, clock=time.monotonic) -> None:
        self._clock = clock
        self._engines: dict[str, EngineHealth] = {}

    # Get (or create) the health record for an engine.
    def _health(self, engine: str) -> EngineHealth:
        health = self._engines.get(engine)
        if health is None:
            health = EngineHealth()
            self._engines[engine] = health
        return health

    # True when the engine may be called right now. A HALF_OPEN engine allows
    # exactly one in-flight probe; callers that get False should use a substitute.
    def allow(self, engine: str) -> bool:
        health = self._health(engine)
        now = self._clock()
        if health.state == BreakerState.CLOSED:
            return True
        if health.state == BreakerState.OPEN:
            if now < health.open_until:
                return False
            health.state = BreakerState.HALF_OPEN
            health.probe_inflight = False
        # HALF_OPEN: admit a single probe. An in-flight probe whose outcome was
        # never recorded (deadline lost the engine event) is expired so it cannot
        # wedge the engine shut forever.
        if health.probe_inflight and (now - health.probe_started) <= PROBE_TIMEOUT:
            return False
        health.probe_inflight = True
        health.probe_started = now
        return True

    # Record the outcome of one engine call (its serp_api payload fields).
    def record(self, engine: str, *, status: str, fetch_ms: float, results: int) -> None:
        health = self._health(engine)
        health.last_status = status
        is_error = status in _ERROR_STATUSES

        spike = (
            not is_error
            and health.ewma_fetch_ms > 0
            and fetch_ms > health.ewma_fetch_ms * _LATENCY_SPIKE_FACTOR
        )
        thin = not is_error and results < _THIN_RESULTS_FLOOR
        is_degraded = spike or thin

        if not is_error and fetch_ms > 0:
            if health.ewma_fetch_ms <= 0:
                health.ewma_fetch_ms = fetch_ms
            else:
                health.ewma_fetch_ms += _EWMA_ALPHA * (fetch_ms - health.ewma_fetch_ms)

        if is_error:
            health.errors += 1
            self._trip(health, ERROR_COOLDOWN)
        elif is_degraded:
            health.degradations += 1
            self._trip(health, DEGRADATION_COOLDOWN)
        else:
            health.successes += 1
            # Success closes the breaker and resets backoff.
            health.state = BreakerState.CLOSED
            health.cooldown = 0.0
            health.probe_inflight = False

    # Open the breaker; a failed half-open probe grows the cooldown exponentially.
    def _trip(self, health: EngineHealth, base_cooldown: float) -> None:
        if health.state == BreakerState.HALF_OPEN and health.cooldown > 0:
            cooldown = min(MAX_COOLDOWN, health.cooldown * BACKOFF_FACTOR)
        else:
            cooldown = base_cooldown
        health.cooldown = cooldown
        health.open_until = self._clock() + cooldown
        health.state = BreakerState.OPEN
        health.probe_inflight = False

    # Snapshot for diagnostics payloads.
    def snapshot(self) -> dict[str, dict[str, object]]:
        now = self._clock()
        out: dict[str, dict[str, object]] = {}
        for engine, health in self._engines.items():
            out[engine] = {
                "state": health.state.value,
                "cooldown_remaining_s": round(max(0.0, health.open_until - now), 1),
                "ewma_fetch_ms": round(health.ewma_fetch_ms, 1),
                "successes": health.successes,
                "errors": health.errors,
                "degradations": health.degradations,
                "last_status": health.last_status,
            }
        return out


# Process-wide tracker shared across searches (engine health is global state).
_shared_tracker: EngineHealthTracker | None = None


def get_health_tracker() -> EngineHealthTracker:
    global _shared_tracker
    if _shared_tracker is None:
        _shared_tracker = EngineHealthTracker()
    return _shared_tracker
