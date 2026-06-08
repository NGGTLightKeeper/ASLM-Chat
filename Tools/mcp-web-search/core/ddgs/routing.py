"""Engine profiles, health state, and conservative search planning."""

from __future__ import annotations

import math
import json
import sqlite3
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EngineProfile:
    name: str
    provider: str
    tier: str
    base_score: float
    specialties: frozenset[str] = frozenset()


PROFILES: dict[str, EngineProfile] = {
    "google": EngineProfile("google", "google", "A", 1.00),
    "duckduckgo": EngineProfile("duckduckgo", "bing", "A", 0.96),
    "brave": EngineProfile("brave", "brave", "A", 0.92),
    "yandex": EngineProfile("yandex", "yandex", "B", 0.80, frozenset({"ru"})),
    "yahoo": EngineProfile("yahoo", "bing", "B", 0.78, frozenset({"zh", "ja", "ko", "finance"})),
    "mojeek": EngineProfile("mojeek", "mojeek", "B", 0.72),
    "startpage": EngineProfile("startpage", "google", "specialized", 0.68),
    "wikipedia": EngineProfile("wikipedia", "wikipedia", "specialized", 0.86, frozenset({"general"})),
    "grokipedia": EngineProfile("grokipedia", "grokipedia", "specialized", 0.45, frozenset({"general"})),
}

LANGUAGE_REGION = {
    "ru": "ru-ru", "zh": "cn-zh", "ja": "jp-ja", "ko": "kr-ko",
    "ar": "ar-ar", "he": "il-he", "th": "th-th", "hi": "in-en", "el": "gr-el",
}
LANGUAGE_PREFERRED = {
    "ru": ("yandex",), "zh": ("yahoo",), "ja": ("yahoo",), "ko": ("yahoo",),
}


def infer_language(query: str) -> str:
    counts = {"ru": 0, "zh": 0, "ja": 0, "ko": 0, "ar": 0, "he": 0, "th": 0, "el": 0}
    total = 0
    for char in query:
        code = ord(char)
        if char.isalpha():
            total += 1
        if 0x0400 <= code <= 0x052F:
            counts["ru"] += 1
        elif 0x4E00 <= code <= 0x9FFF:
            counts["zh"] += 1
        elif 0x3040 <= code <= 0x30FF:
            counts["ja"] += 1
        elif 0xAC00 <= code <= 0xD7AF:
            counts["ko"] += 1
        elif 0x0600 <= code <= 0x06FF:
            counts["ar"] += 1
        elif 0x0590 <= code <= 0x05FF:
            counts["he"] += 1
        elif 0x0E00 <= code <= 0x0E7F:
            counts["th"] += 1
        elif 0x0370 <= code <= 0x03FF:
            counts["el"] += 1
    language, count = max(counts.items(), key=lambda item: item[1])
    return language if count >= max(1, total * 0.15) else "en"


@dataclass(slots=True)
class HealthState:
    latencies: deque[float] = field(default_factory=lambda: deque(maxlen=30))
    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    suspended_until: float = 0.0
    last_used_at: float = 0.0

    @property
    def suspended(self) -> bool:
        return time.time() < self.suspended_until

    @property
    def p50(self) -> float | None:
        return statistics.median(self.latencies) if self.latencies else None

    @property
    def p95(self) -> float | None:
        if not self.latencies:
            return None
        values = sorted(self.latencies)
        return values[max(0, math.ceil(len(values) * 0.95) - 1)]

    @property
    def success_rate(self) -> float:
        total = self.successes + self.failures
        return self.successes / total if total else 0.65


class RoutingState:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._lock = threading.RLock()
        self._db_path = str(db_path) if db_path else None
        self.engines: dict[str, HealthState] = {}
        self.providers: dict[str, HealthState] = {}
        if self._db_path:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ddgs_routing_state (
                        kind TEXT NOT NULL,
                        name TEXT NOT NULL,
                        latencies TEXT NOT NULL,
                        successes INTEGER NOT NULL,
                        failures INTEGER NOT NULL,
                        consecutive_failures INTEGER NOT NULL,
                        suspended_until REAL NOT NULL,
                        last_used_at REAL NOT NULL,
                        PRIMARY KEY (kind, name)
                    )
                    """
                )

    def _refresh(self) -> None:
        if not self._db_path:
            return
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute("SELECT * FROM ddgs_routing_state").fetchall()
        for kind, name, latencies, successes, failures, consecutive, suspended, last_used in rows:
            target = self.engines if kind == "engine" else self.providers
            target[name] = HealthState(
                latencies=deque(json.loads(latencies), maxlen=30),
                successes=successes,
                failures=failures,
                consecutive_failures=consecutive,
                suspended_until=suspended,
                last_used_at=last_used,
            )

    def _save(self, kind: str, name: str, state: HealthState) -> None:
        if not self._db_path:
            return
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ddgs_routing_state
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kind, name, json.dumps(list(state.latencies)), state.successes, state.failures,
                    state.consecutive_failures, state.suspended_until, state.last_used_at,
                ),
            )

    def engine(self, name: str) -> HealthState:
        with self._lock:
            return self.engines.setdefault(name, HealthState())

    def provider(self, name: str) -> HealthState:
        with self._lock:
            return self.providers.setdefault(name, HealthState())

    def attempt_timeout(self, name: str, hard_timeout: float) -> float:
        p95 = self.engine(name).p95
        if p95 is None:
            return hard_timeout
        return max(2.0, min(hard_timeout, p95 * 1.5 + 0.5))

    def record(self, name: str, latency: float, success: bool, error: BaseException | None = None) -> None:
        profile = PROFILES[name]
        with self._lock:
            engine = self.engine(name)
            provider = self.provider(profile.provider)
            for state in (engine, provider):
                state.last_used_at = time.time()
                if success:
                    state.latencies.append(latency)
                    state.successes += 1
                    state.consecutive_failures = 0
                else:
                    state.failures += 1
                    state.consecutive_failures += 1
            if not success:
                message = str(error or "").lower()
                if "captcha" in message:
                    delay = 3600.0
                elif "429" in message or "rate" in message:
                    delay = 180.0
                elif "403" in message or "forbidden" in message:
                    delay = 180.0
                elif "timeout" in message or "timed out" in message:
                    delay = min(120.0, 5.0 * engine.consecutive_failures)
                else:
                    delay = min(120.0, 5.0 * engine.consecutive_failures)
                engine.suspended_until = time.time() + delay
            self._save("engine", name, engine)
            self._save("provider", profile.provider, provider)

    def score(self, profile: EngineProfile, language: str, query_types: set[str]) -> float:
        engine = self.engine(profile.name)
        provider = self.provider(profile.provider)
        score = profile.base_score
        if engine.p50 is not None:
            score -= min(0.35, engine.p50 / 20.0)
        score += 0.20 * engine.success_rate
        score += 0.20 if profile.name in LANGUAGE_PREFERRED.get(language, ()) else 0.0
        score += 0.10 if profile.specialties & query_types else 0.0
        score -= 0.15 if profile.tier == "specialized" and not profile.specialties & query_types else 0.0
        score -= min(0.20, provider.consecutive_failures * 0.05)
        now = time.time()
        if engine.last_used_at:
            score -= max(0.0, 0.10 * (1.0 - (now - engine.last_used_at) / 15.0))
        if provider.last_used_at:
            score -= max(0.0, 0.15 * (1.0 - (now - provider.last_used_at) / 30.0))
        return score

    def plan(
        self,
        available: set[str],
        *,
        language: str,
        query_types: set[str],
        max_attempts: int,
    ) -> list[str]:
        with self._lock:
            self._refresh()
        candidates = [PROFILES[name] for name in available if name in PROFILES and not self.engine(name).suspended]
        if not candidates:
            candidates = [PROFILES[name] for name in available if name in PROFILES]
        candidates.sort(key=lambda profile: self.score(profile, language, query_types), reverse=True)

        plan: list[str] = []
        used_providers: set[str] = set()
        for profile in candidates:
            if profile.provider in used_providers:
                continue
            plan.append(profile.name)
            used_providers.add(profile.provider)
            if len(plan) >= max_attempts:
                return plan
        for profile in candidates:
            if profile.name not in plan:
                plan.append(profile.name)
                if len(plan) >= max_attempts:
                    break
        return plan


_STATE_DB = Path(__file__).resolve().parents[2] / "tmp" / "ddgs_routing_state.sqlite"
ROUTING_STATE = RoutingState(_STATE_DB)
