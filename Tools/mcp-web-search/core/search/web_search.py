# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Web-search orchestrator: stream → triage → bounded eager parse scheduler.

Wires the live SERP stream to incremental triage and an eager parse scheduler:

    search_stream → source event → triage.ingest (~0.1 ms)
        ├─ PARSE  → fetch/parse starts immediately (bounded slots)
        ├─ QUEUE  → held; consensus votes may upgrade it mid-stream
        └─ SKIP   → dropped

Engine selection is tier-based (low/medium/high) and gated by the per-engine
circuit breaker. Parsing of early winners overlaps the tail of slow engines, so
parse latency hides inside SERP latency.

Process discipline (non-negotiable): every parse task is tracked and cancelled
at the deadline; cancellation propagates into the read service, whose camoufox
path kills the worker process tree on CancelledError. No fire-and-forget tasks.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
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
from .health import EngineHealthTracker, get_health_tracker
from .quality import infer_query_language
from .serp_api import SerpApi, _get_transport
from .triage import TriageAction, TriageSession

logger = logging.getLogger("services.web_search")
trace_logger = logging.getLogger("trace.web_search")

# Engines take the parser's max; final cut happens after triage, not at the engine
# (the parser scans the whole page either way — trimming early just wastes results).
_SOURCE_LIMIT = 20


# Per-effort budgets. parse_budget=0 means SERP-only (low is a fast path).
@dataclass(frozen=True, slots=True)
class EffortProfile:
    name: str
    parse_budget: int  # total pages parsed per search
    parse_concurrency: int  # parallel parse slots
    parse_reserve: int  # slots held back until the stream ends (anti-greed)
    parse_timeout: float  # hard cap per page parse
    parse_max_chars: int
    deadline: float  # hard cap for the whole search
    max_results: int  # sources returned after ranking


EFFORT_PROFILES: dict[str, EffortProfile] = {
    "low": EffortProfile("low", 0, 0, 0, 0.0, 0, 12.0, 8),
    "medium": EffortProfile("medium", 4, 3, 1, 12.0, 8_000, 25.0, 10),
    "high": EffortProfile("high", 8, 3, 1, 18.0, 20_000, 50.0, 16),
}


# Pick engines for a tier, honoring the circuit breaker (TODO.md §6).
# Never returns an empty list: low's lead pair falls back to Startpage, and as a
# last resort Yandex is forced even through an open breaker.
def select_engines(effort: str, tracker: EngineHealthTracker) -> list[type]:
    selected: list[type] = []

    # low core: Yandex (default) + DDG (lead, breaker-gated).
    if tracker.allow(YandexParser.name):
        selected.append(YandexParser)
    if tracker.allow(DuckDuckGoParser.name):
        selected.append(DuckDuckGoParser)
    if not selected:
        # Both leads are cooling down — pull the reserve.
        if tracker.allow(StartpageParser.name):
            selected.append(StartpageParser)
        else:
            selected.append(YandexParser)  # forced: low must never be empty

    if effort == "low":
        return selected

    # medium: one google-family slot (Google primary, Startpage hot standby)…
    if tracker.allow(GoogleParser.name):
        selected.append(GoogleParser)
    elif StartpageParser not in selected and tracker.allow(StartpageParser.name):
        selected.append(StartpageParser)
    # …plus Qwant as a health-gated helper.
    if tracker.allow(QwantParser.name):
        selected.append(QwantParser)

    if effort == "medium":
        return selected

    # high: Brave (rate-governed by its breaker) and Yep (max recall).
    if tracker.allow(BraveParser.name):
        selected.append(BraveParser)
    if tracker.allow(YepParser.name):
        selected.append(YepParser)
    return selected


# One aggregated source row under construction.
@dataclass(slots=True)
class _Source:
    url: str
    host: str
    title: str
    snippet: str
    engine: str  # first engine that surfaced it
    rank: int
    score: float
    families: list[str]
    parsed_markdown: str = ""
    parsed_ok: bool = False
    parse_ms: float = 0.0


# Orchestrates one search: stream → triage → bounded eager parsing → ranking.
class WebSearchService:

    def __init__(
        self,
        *,
        tracker: EngineHealthTracker | None = None,
        read_page=None,
    ) -> None:
        self._tracker = tracker or get_health_tracker()
        # Injectable for tests; default import is deferred so SERP-only paths
        # never pay for the read service's heavy imports.
        self._read_page = read_page

    # Resolve the page reader lazily.
    def _reader(self):
        if self._read_page is None:
            from core.read.service import run_read_page

            self._read_page = run_read_page
        return self._read_page

    # Parse one URL under its own hard timeout; never raises.
    async def _parse_one(self, source: _Source, profile: EffortProfile) -> None:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(profile.parse_timeout):
                markdown = await self._reader()(
                    source.url,
                    timeout=profile.parse_timeout,
                    max_chars=profile.parse_max_chars,
                    allow_browser=False,  # search is HTTP-only; browser is read_page-exclusive
                )
            source.parsed_markdown = markdown or ""
            source.parsed_ok = bool(markdown) and not markdown.startswith("Error:")
        except (TimeoutError, asyncio.CancelledError):
            source.parsed_markdown = ""
            source.parsed_ok = False
            raise
        except Exception as exc:  # noqa: BLE001 — a failed parse must not sink the search
            logger.debug("parse failed for %s: %s", source.url, exc)
            source.parsed_ok = False
        finally:
            source.parse_ms = (time.perf_counter() - started) * 1000

    # Run one full search. Returns the aggregated, ranked payload.
    async def search(
        self,
        query: str,
        *,
        effort: str = "low",
        region: str = "",
        safesearch: str = "moderate",
        timelimit: str | None = None,
    ) -> dict[str, Any]:
        profile = EFFORT_PROFILES.get(effort, EFFORT_PROFILES["low"])
        started = time.perf_counter()

        # Region routing (§3.2): explicit region wins; otherwise Cyrillic and
        # friends route to their home region instead of us-en.
        language = infer_query_language(query)
        if not region:
            region = {"ru": "ru-ru", "de": "de-de"}.get(language, "us-en")

        engines = select_engines(profile.name, self._tracker)
        logger.info(
            "web_search.start effort=%s region=%s language=%s engines=%s query=%r",
            profile.name, region, language, [e.name for e in engines], query[:160],
        )
        api = SerpApi(
            transport=_get_transport(8.0),
            timeout_seconds=8.0,
            source_limit=_SOURCE_LIMIT,
            engines=tuple(engines),
        )

        triage = TriageSession(query)
        sources: dict[str, _Source] = {}
        queue: list[str] = []  # urls in QUEUE state
        engine_payloads: dict[str, dict[str, Any]] = {}
        parse_tasks: dict[str, asyncio.Task[None]] = {}
        parse_started_count = 0
        slots = asyncio.Semaphore(max(1, profile.parse_concurrency)) if profile.parse_budget else None
        budget_during_stream = max(0, profile.parse_budget - profile.parse_reserve)

        # Spawn a tracked parse task for a triaged source.
        def spawn_parse(url: str) -> None:
            nonlocal parse_started_count
            if profile.parse_budget == 0 or url in parse_tasks:
                return
            if parse_started_count >= profile.parse_budget:
                return
            source = sources[url]
            parse_started_count += 1

            async def run() -> None:
                assert slots is not None
                async with slots:
                    await self._parse_one(source, profile)

            parse_tasks[url] = asyncio.create_task(run(), name=f"parse:{source.host}")

        try:
            async with asyncio.timeout(profile.deadline):
                async for event in api.search_stream(
                    query,
                    region=region,
                    safesearch=safesearch,
                    timelimit=timelimit,
                    deadline_seconds=profile.deadline * 0.8,
                ):
                    kind = event["type"]
                    if kind == "source":
                        url = event["url"]["url"]
                        decision = triage.ingest_source(
                            engine=event["engine"],
                            provider_family=event["provider_family"],
                            rank=event["rank"],
                            url=url,
                            title=event["serp"]["title"],
                            snippet=event["serp"]["snippet"],
                        )
                        if decision.action == TriageAction.SKIP:
                            continue
                        sources[url] = _Source(
                            url=url,
                            host=event["url"]["host"],
                            title=event["serp"]["title"],
                            snippet=event["serp"]["snippet"],
                            engine=event["engine"],
                            rank=event["rank"],
                            score=decision.score,
                            families=[event["provider_family"]],
                        )
                        trace_logger.info(
                            "source engine=%s family=%s rank=%d action=%s score=%.3f url=%r",
                            event["engine"], event["provider_family"], event["rank"],
                            decision.action.name, decision.score, url,
                        )
                        if decision.action == TriageAction.PARSE and parse_started_count < budget_during_stream:
                            spawn_parse(url)
                        else:
                            queue.append(url)
                    elif kind == "vote":
                        url = event["url"]["url"]
                        decision = triage.ingest_vote(
                            provider_family=event["provider_family"], url=url
                        )
                        source = sources.get(url)
                        if source is not None:
                            if event["provider_family"] not in source.families:
                                source.families.append(event["provider_family"])
                            source.score = triage.score_of(url)
                        if (
                            decision is not None
                            and decision.upgraded
                            and parse_started_count < budget_during_stream
                        ):
                            with contextlib.suppress(ValueError):
                                queue.remove(url)
                            spawn_parse(url)
                    elif kind == "engine":
                        payload = event["payload"]
                        engine_payloads[payload["engine"]] = payload
                        self._tracker.record(
                            payload["engine"],
                            status=payload["status"],
                            fetch_ms=payload["fetch_ms"],
                            results=len(payload["sources"]),
                        )

                # Stream done: spend remaining budget (incl. reserve) on the best
                # queued sources at full-picture scores.
                if profile.parse_budget:
                    queue.sort(key=triage.score_of, reverse=True)
                    for url in queue:
                        if parse_started_count >= profile.parse_budget:
                            break
                        spawn_parse(url)
                    if parse_tasks:
                        await asyncio.gather(*parse_tasks.values(), return_exceptions=True)
        except TimeoutError:
            logger.warning("web_search deadline %.0fs hit for query=%r", profile.deadline, query)
        finally:
            # Hard rule: no task survives the search. Cancellation propagates into
            # read_page → camoufox worker kill.
            pending = [task for task in parse_tasks.values() if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        ranked = sorted(sources.values(), key=lambda s: s.score, reverse=True)
        top = ranked[: profile.max_results]
        parsed_ok = sum(1 for s in top if s.parsed_ok)
        logger.info(
            "web_search.done effort=%s sources=%d parsed=%d/%d elapsed_ms=%.0f query=%r",
            profile.name, len(top), parsed_ok, parse_started_count,
            (time.perf_counter() - started) * 1000, query[:160],
        )
        return {
            "query": query,
            "effort": profile.name,
            "language": language,
            "region": region,
            "engines_used": [engine.name for engine in engines],
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "sources": [
                {
                    "url": s.url,
                    "host": s.host,
                    "title": s.title,
                    "snippet": s.snippet,
                    "engine": s.engine,
                    "rank": s.rank,
                    "score": round(s.score, 4),
                    "consensus_families": s.families,
                    **(
                        {
                            "parsed_ok": s.parsed_ok,
                            "parse_ms": round(s.parse_ms, 1),
                            "markdown": s.parsed_markdown,
                        }
                        if s.parse_ms or s.parsed_markdown
                        else {}
                    ),
                }
                for s in top
            ],
            "engines": engine_payloads,
            "health": self._tracker.snapshot(),
        }


# Convenience entry point mirroring run_serp_search.
async def run_web_search(
    query: str,
    *,
    effort: str = "low",
    region: str = "",
    safesearch: str = "moderate",
    timelimit: str | None = None,
) -> dict[str, Any]:
    service = WebSearchService()
    return await service.search(
        query, effort=effort, region=region, safesearch=safesearch, timelimit=timelimit
    )
