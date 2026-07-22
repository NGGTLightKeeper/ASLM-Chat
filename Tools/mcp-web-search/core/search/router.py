# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Automatic advanced-search pressure accounting and provider routing."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any

from ..engines import (
    BraveParser,
    DuckDuckGoParser,
    GoogleParser,
    QwantParser,
    StartpageParser,
    YandexParser,
    YepParser,
)


THROTTLE_NAMES = ("normal", "T1", "T2", "T3", "T4")
SCRAPER_TYPES = (
    GoogleParser,
    DuckDuckGoParser,
    StartpageParser,
    QwantParser,
    BraveParser,
    YandexParser,
    YepParser,
)
SCRAPER_BY_NAME = {parser.name: parser for parser in SCRAPER_TYPES}
_PRIORITY = {
    "yandex": 100,
    "duckduckgo": 90,
    "qwant": 80,
    "brave": 75,
    "google": 70,
    "yep": 50,
    "startpage": 45
}
_VERTICAL_WEIGHTS = {"web": 1.0, "shopping": 1.25, "academic": 1.25, "onion": 1.1}


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    name: str
    kind: str
    family: str
    priority: int = 0


@dataclass(slots=True)
class _PressureState:
    pressure: float = 0.0
    level: int = 0
    burst_count: int = 0
    last_activity: float = 0.0


@dataclass(frozen=True, slots=True)
class SearchRoutingDecision:
    scope: str
    requested_count: int
    admitted_count: int
    dropped_indices: tuple[int, ...]
    level: int
    level_name: str
    pressure: float
    request_cost: float
    burst_multiplier: float
    api_relief_factor: float
    api_providers: tuple[str, ...]
    api_families: tuple[str, ...]
    primary_by_query: tuple[tuple[str, ...], ...]
    reserve_scrapers: tuple[str, ...]
    parse_budgets: tuple[int, ...]
    max_results_per_query: int
    browser_permits: int
    recovery_seconds: float

    @property
    def primary_scrapers(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(name for group in self.primary_by_query for name in group))

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "requested_queries": self.requested_count,
            "executed_queries": self.admitted_count,
            "dropped_query_indices": list(self.dropped_indices),
            "throttle": self.level_name,
            "pressure": round(self.pressure, 3),
            "request_cost": round(self.request_cost, 3),
            "burst_multiplier": round(self.burst_multiplier, 3),
            "api_relief_factor": round(self.api_relief_factor, 3),
            "api_providers": list(self.api_providers),
            "api_families": list(self.api_families),
            "primary_scrapers": [list(group) for group in self.primary_by_query],
            "reserve_scrapers": list(self.reserve_scrapers),
            "parse_budgets": list(self.parse_budgets),
            "max_results_per_query": self.max_results_per_query,
            "browser_permits": self.browser_permits,
            "recovery_seconds": self.recovery_seconds,
        }


class SearchPressureController:
    """Process-local, generation-scoped pressure state with atomic routing decisions."""

    def __init__(self, *, clock=time.monotonic) -> None:
        self._clock = clock
        self._states: dict[str, _PressureState] = {}
        self._last_used: dict[str, float] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _level_for(pressure: float, thresholds: list[float]) -> int:
        return sum(pressure >= threshold for threshold in thresholds)

    @staticmethod
    def _burst_multiplier(count: int) -> float:
        if count <= 1:
            return 0.85
        if count == 2:
            return 0.90
        if count == 3:
            return 0.95
        return min(1.50, 0.95 + 0.10 * (count - 3))

    @staticmethod
    def _distribute(total: int, count: int) -> tuple[int, ...]:
        if count <= 0:
            return ()
        base, extra = divmod(max(0, total), count)
        return tuple(base + (1 if index < extra else 0) for index in range(count))

    def _recover(self, state: _PressureState, now: float, cfg) -> None:
        if not state.last_activity:
            return
        idle = max(0.0, now - state.last_activity)
        steps = int(idle // cfg.idle_recovery_seconds)
        if steps <= 0:
            return
        state.level = max(0, state.level - steps)
        if state.level == 0:
            state.pressure = 0.0
        else:
            state.pressure = min(
                state.pressure,
                float(cfg.pressure_thresholds[state.level - 1]),
            )
        state.burst_count = 0

    def _ordered_scrapers(self, tracker, enabled: dict[str, bool], now: float) -> list[str]:
        candidates = [
            parser.name
            for parser in SCRAPER_TYPES
            if enabled.get(parser.name, True)
            and (
                tracker.can_attempt(parser.name)
                if hasattr(tracker, "can_attempt")
                else tracker.is_healthy(parser.name)
            )
        ]
        return sorted(
            candidates,
            key=lambda name: (-_PRIORITY.get(name, 0), self._last_used.get(name, 0.0), name),
        )

    def decide(
        self,
        plans: list[dict[str, Any]],
        *,
        scope: str,
        api_providers: list[ProviderDescriptor],
        tracker,
        enabled_scrapers: dict[str, bool],
        cfg,
    ) -> SearchRoutingDecision:
        now = self._clock()
        requested_count = max(1, len(plans))
        clean_scope = scope.strip() or "process:<unknown>"

        with self._lock:
            for key, old in list(self._states.items()):
                if old.last_activity and now - old.last_activity > cfg.state_ttl_seconds:
                    self._states.pop(key, None)
            state = self._states.setdefault(clean_scope, _PressureState())
            idle = now - state.last_activity if state.last_activity else float("inf")
            self._recover(state, now, cfg)
            state.burst_count = state.burst_count + 1 if idle < cfg.idle_recovery_seconds else 1

            burst = self._burst_multiplier(state.burst_count)
            api_count = len(api_providers)
            relief = float(cfg.api_relief_factors[min(api_count, len(cfg.api_relief_factors) - 1)])
            weighted = sum(
                _VERTICAL_WEIGHTS.get(str(plan.get("vertical") or "web"), 1.0)
                for plan in plans
            ) or 1.0
            raw_cost = weighted * (1.0 + 0.25 * (requested_count - 1))
            request_cost = raw_cost * burst * relief
            state.pressure = min(float(cfg.pressure_thresholds[-1]), state.pressure + request_cost)
            state.level = self._level_for(state.pressure, list(cfg.pressure_thresholds))
            state.last_activity = now

            admitted = min(requested_count, int(cfg.batch_caps[state.level]))
            dropped = tuple(range(admitted + 1, requested_count + 1))
            api_names = tuple(provider.name for provider in api_providers)
            api_families = tuple(dict.fromkeys(provider.family for provider in api_providers))

            ordered = self._ordered_scrapers(tracker, enabled_scrapers, now)
            desired_reserve = (
                int(cfg.reserve_high)
                if api_count >= int(cfg.reserve_api_threshold)
                else int(cfg.reserve_low)
            )
            if state.level == 4:
                desired_reserve = max(2, desired_reserve)
            reserve_count = min(desired_reserve, max(0, len(ordered) - 1))
            reserve: list[str] = []
            if reserve_count:
                # Startpage is Google's natural standby; remaining reserves come from
                # the tail so privileged primary engines stay available for single-query work.
                if "startpage" in ordered:
                    reserve.append("startpage")
                for name in reversed(ordered):
                    if len(reserve) >= reserve_count:
                        break
                    if name not in reserve:
                        reserve.append(name)
            primary_pool = [name for name in ordered if name not in reserve]

            factor = float(cfg.scraper_factors[state.level])
            per_query = (
                0
                if factor <= 0 or not primary_pool
                else max(1, math.ceil(len(primary_pool) * factor / admitted))
            )
            primary_by_query: list[tuple[str, ...]] = []
            cursor = 0
            allowed_this_call: set[str] = set()
            for _index in range(admitted):
                chosen: list[str] = []
                attempts = 0
                while len(chosen) < per_query and attempts < max(1, len(primary_pool) * 2):
                    name = primary_pool[cursor % len(primary_pool)]
                    cursor += 1
                    attempts += 1
                    if name in chosen:
                        continue
                    if name not in allowed_this_call:
                        if not tracker.allow(name):
                            continue
                        allowed_this_call.add(name)
                    chosen.append(name)
                    self._last_used[name] = now
                if not chosen and per_query and primary_pool:
                    chosen.append(primary_pool[cursor % len(primary_pool)])
                primary_by_query.append(tuple(chosen))

            parse_budgets = self._distribute(int(cfg.parse_budgets[state.level]), admitted)
            max_results = max(6, math.ceil(int(cfg.max_results[state.level]) / admitted))
            browser_permits = 1 if state.level == 0 and admitted == 1 else 0
            recovery_seconds = float(cfg.idle_recovery_seconds if state.level else 0.0)
            return SearchRoutingDecision(
                scope=clean_scope,
                requested_count=requested_count,
                admitted_count=admitted,
                dropped_indices=dropped,
                level=state.level,
                level_name=THROTTLE_NAMES[state.level],
                pressure=state.pressure,
                request_cost=request_cost,
                burst_multiplier=burst,
                api_relief_factor=relief,
                api_providers=api_names,
                api_families=api_families,
                primary_by_query=tuple(primary_by_query),
                reserve_scrapers=tuple(reserve),
                parse_budgets=parse_budgets,
                max_results_per_query=max_results,
                browser_permits=browser_permits,
                recovery_seconds=recovery_seconds,
            )


_CONTROLLER: SearchPressureController | None = None


def get_search_pressure_controller() -> SearchPressureController:
    global _CONTROLLER
    if _CONTROLLER is None:
        _CONTROLLER = SearchPressureController()
    return _CONTROLLER


def routing_scope(context: dict[str, Any] | None) -> str:
    safe = context or {}
    generation_id = str(safe.get("generation_id") or "").strip()
    if generation_id:
        return f"generation:{generation_id}"
    chat_id = str(safe.get("chat_id") or "").strip()
    return f"chat:{chat_id}" if chat_id else "process:<unknown>"
