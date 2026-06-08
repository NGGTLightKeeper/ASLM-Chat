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
    "brave_news": EngineProfile("brave_news", "brave", "specialized", 0.90, frozenset({"journalistic", "news"})),
    "bing": EngineProfile("bing", "bing", "B", 0.84),
    "bing_news": EngineProfile("bing_news", "bing", "specialized", 0.84, frozenset({"journalistic", "news"})),
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

# Query classification affects the first engine choice, not only result triage.
# Values are additive affinity multipliers applied to the weighted class mix.
ENGINE_CLASS_AFFINITY: dict[str, dict[str, float]] = {
    "google": {
        "documentation": 0.34, "technical": 0.28, "legal": 0.30,
        "medical": 0.27, "academic": 0.24, "finance": 0.18,
        "government": 0.30,
    },
    "brave": {
        "technical": 0.24, "documentation": 0.20, "journalistic": 0.20,
        "news": 0.20, "legal": 0.12, "forum": 0.10,
    },
    "duckduckgo": {"general": 0.08, "forum": 0.16, "troubleshooting": 0.12},
    "brave_news": {"journalistic": 0.55, "news": 0.55, "finance": 0.18},
    "bing": {"finance": 0.18, "legal": 0.14, "government": 0.14},
    "bing_news": {"journalistic": 0.50, "news": 0.50, "finance": 0.18},
    "yahoo": {"finance": 0.28},
    "startpage": {
        "legal": 0.22, "medical": 0.20, "documentation": 0.18,
        "government": 0.18,
    },
    "wikipedia": {"general": 0.20, "education": 0.16},
}
EARLY_SPECIALIST_CLASSES = frozenset({"journalistic", "news"})


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
    consecutive_timeouts: int = 0
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
                        consecutive_timeouts INTEGER NOT NULL DEFAULT 0,
                        suspended_until REAL NOT NULL,
                        last_used_at REAL NOT NULL,
                        PRIMARY KEY (kind, name)
                    )
                    """
                )
                columns = {row[1] for row in conn.execute("PRAGMA table_info(ddgs_routing_state)")}
                if "consecutive_timeouts" not in columns:
                    conn.execute(
                        "ALTER TABLE ddgs_routing_state "
                        "ADD COLUMN consecutive_timeouts INTEGER NOT NULL DEFAULT 0"
                    )

    def _refresh(self) -> None:
        if not self._db_path:
            return
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT kind, name, latencies, successes, failures, consecutive_failures, "
                "consecutive_timeouts, suspended_until, last_used_at FROM ddgs_routing_state"
            ).fetchall()
        for kind, name, latencies, successes, failures, consecutive, timeouts, suspended, last_used in rows:
            target = self.engines if kind == "engine" else self.providers
            target[name] = HealthState(
                latencies=deque(json.loads(latencies), maxlen=30),
                successes=successes,
                failures=failures,
                consecutive_failures=consecutive,
                consecutive_timeouts=timeouts,
                suspended_until=suspended,
                last_used_at=last_used,
            )

    def _save(self, kind: str, name: str, state: HealthState) -> None:
        if not self._db_path:
            return
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ddgs_routing_state (
                    kind, name, latencies, successes, failures, consecutive_failures,
                    consecutive_timeouts, suspended_until, last_used_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kind, name, json.dumps(list(state.latencies)), state.successes, state.failures,
                    state.consecutive_failures, state.consecutive_timeouts,
                    state.suspended_until, state.last_used_at,
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
        message = str(error or "").lower()
        timed_out = "timeout" in message or "timed out" in message
        with self._lock:
            engine = self.engine(name)
            provider = self.provider(profile.provider)
            for state in (engine, provider):
                state.last_used_at = time.time()
                if success:
                    state.latencies.append(latency)
                    state.successes += 1
                    state.consecutive_failures = 0
                    state.consecutive_timeouts = 0
                    state.suspended_until = 0.0
                else:
                    state.failures += 1
                    state.consecutive_failures += 1
                    state.consecutive_timeouts = state.consecutive_timeouts + 1 if timed_out else 0
            if not success:
                if "captcha" in message:
                    delay = (120.0, 600.0, 1800.0)[min(engine.consecutive_failures - 1, 2)]
                elif "429" in message or "rate" in message:
                    delay = (20.0, 60.0, 180.0)[min(engine.consecutive_failures - 1, 2)]
                elif "403" in message or "forbidden" in message:
                    delay = (8.0, 30.0, 120.0)[min(engine.consecutive_failures - 1, 2)]
                elif "timeout" in message or "timed out" in message:
                    delay = min(60.0, 3.0 * engine.consecutive_failures)
                else:
                    delay = min(60.0, 3.0 * engine.consecutive_failures)
                engine.suspended_until = time.time() + delay
            self._save("engine", name, engine)
            self._save("provider", profile.provider, provider)

    def quality_concurrency(self, available: set[str]) -> int:
        """Use two workers normally, then serialize after repeated timeout pressure."""
        with self._lock:
            states = [self.engine(name) for name in available if name in PROFILES]
            timeout_engines = sum(state.consecutive_timeouts > 0 for state in states)
            max_streak = max((state.consecutive_timeouts for state in states), default=0)
        return 1 if max_streak >= 2 or timeout_engines >= 2 else 2

    def score(
        self,
        profile: EngineProfile,
        language: str,
        query_types: set[str],
        class_weights: dict[str, float] | None = None,
    ) -> float:
        engine = self.engine(profile.name)
        provider = self.provider(profile.provider)
        weights = class_weights or {query_type: 1.0 for query_type in query_types}
        total_weight = sum(max(0.0, float(weight)) for weight in weights.values()) or 1.0
        score = profile.base_score
        if engine.p50 is not None:
            score -= min(0.35, engine.p50 / 20.0)
        score += 0.20 * engine.success_rate
        score += 0.20 if profile.name in LANGUAGE_PREFERRED.get(language, ()) else 0.0
        score += sum(
            max(0.0, float(weight)) * ENGINE_CLASS_AFFINITY.get(profile.name, {}).get(query_type, 0.0)
            for query_type, weight in weights.items()
        ) / total_weight
        specialty_weight = sum(
            max(0.0, float(weights.get(specialty, 0.0)))
            for specialty in profile.specialties
        ) / total_weight
        score += 0.22 * specialty_weight
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
        class_weights: dict[str, float] | None = None,
        max_attempts: int,
        prefer_tier: str | None = None,
        routing_profile: str = "stability",
    ) -> list[str]:
        with self._lock:
            self._refresh()
        candidates = [PROFILES[name] for name in available if name in PROFILES and not self.engine(name).suspended]
        if not candidates:
            candidates = [PROFILES[name] for name in available if name in PROFILES]
        candidates.sort(
            key=lambda profile: self.score(profile, language, query_types, class_weights),
            reverse=True,
        )
        if prefer_tier:
            candidates.sort(key=lambda profile: profile.tier != prefer_tier)

        plan: list[str] = []
        used_providers: set[str] = set()
        if routing_profile == "stability" and not prefer_tier and max_attempts >= 2:
            weights = class_weights or {query_type: 1.0 for query_type in query_types}
            total_weight = sum(max(0.0, float(weight)) for weight in weights.values()) or 1.0
            dominant_class, dominant_weight = max(
                weights.items(),
                key=lambda item: float(item[1]),
                default=("general", 0.0),
            )
            dominant_share = max(0.0, float(dominant_weight)) / total_weight
            specialist = next(
                (
                    profile for profile in candidates
                    if profile.tier == "specialized"
                    and dominant_class in profile.specialties
                    and dominant_class in EARLY_SPECIALIST_CLASSES
                    and dominant_share >= 0.40
                ),
                None,
            )
            best_a = next((profile for profile in candidates if profile.tier == "A"), None)
            best_b = next((profile for profile in candidates if profile.tier == "B"), None)
            for profile in (specialist, best_a, best_b):
                if profile is None or profile.name in plan:
                    continue
                plan.append(profile.name)
                used_providers.add(profile.provider)
                if len(plan) >= max_attempts:
                    return plan
        for profile in candidates:
            if profile.name in plan:
                continue
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
