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
at the deadline. No fire-and-forget tasks. The persistent warm browser lives in
its own daemon, so a cancelled search never leaves a browser process behind.
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

# A domain the runtime profile store has learned to fetch slower than this is left
# snippet-only in search (still readable via read_page). Tighter than read_page's own
# avoid bar — a wide search cannot afford a multi-second page on the hot path.
_INLINE_PARSE_SKIP_MS = 6_000.0


# Whether a source may be parsed inline during a search, or should stay snippet-only.
# Two reasons to skip: a read_page-only custom-domain handler (reddit/x/ebay/youtube —
# browser/slow APIs), or a domain the runtime store has learned is too slow to parse.
# Either way the source still ranks and is returned; only its page is left for read_page.
def _inline_parse_allowed(url: str) -> bool:
    try:
        import custom_domains

        if custom_domains.is_read_page_only(url):
            return False
    except Exception:  # noqa: BLE001 — a handler lookup must never sink a search
        pass
    try:
        from core.profiles import domain_of, get_runtime_profiles

        hint = get_runtime_profiles().best_method(domain_of(url))
    except Exception:  # noqa: BLE001 — a profile lookup must never sink a search
        return True
    return not (hint and hint.expected_fetch_ms > _INLINE_PARSE_SKIP_MS)


# Resolve a direct PDF URL for a result (already a PDF, or an arXiv abs → pdf link).
# Ported from the legacy _infer_pdf_url so the model still gets direct PDF links.
def _infer_pdf_url(url: str) -> str:
    from core.extract.pdf_extractor import looks_like_pdf_url

    u = (url or "").strip()
    if not u:
        return ""
    if looks_like_pdf_url(u):
        return u
    if "arxiv.org/abs/" in u:
        return u.replace("/abs/", "/pdf/", 1)
    return ""


# Per-effort contracts. Each tier is a distinct deal, not just a bigger budget:
#
#   low    — SERP-only. Pure HTTP, NO page parse, no browser, no model. Sub-2s.
#   medium — HTTP page parsing only (no browser, no model). Hard-bounded to ~6-8s total:
#            tight per-page parse cap and a short overall deadline.
#   high   — deeper HTTP parse + limited warm-browser escalation + a CPU decoder
#            re-ranker. The browser/decoder allowances are declared here; their wiring
#            (read/service warm-browser, decoder content-stage) lands separately.
#
# parse_budget=0 means SERP-only. parse_timeout is the hard per-page cap (6s ceiling —
# a wide search cannot afford a slow page; slow domains are left snippet-only anyway).
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
    allow_browser: bool  # high only: limited warm-browser escalation (HTTP-only until wired)
    allow_decoder: bool  # high only: CPU decoder content-stage re-ranker (pending integration)


EFFORT_PROFILES: dict[str, EffortProfile] = {
    "low": EffortProfile("low", 0, 0, 0, 0.0, 0, 8.0, 8, False, False),
    "medium": EffortProfile("medium", 3, 3, 1, 6.0, 8_000, 8.0, 10, False, False),
    "high": EffortProfile("high", 8, 4, 1, 8.0, 20_000, 22.0, 16, True, True),
}


# Pick engines for a tier, honoring the circuit breaker.
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
    decoder_score: float = -1.0  # >=0 once the high-effort decoder re-ranker has scored it


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
                    # Search stays HTTP-only: the warm browser is exclusive to the
                    # read_page tool. Flip to profile.allow_browser to let high effort
                    # escalate to the warm daemon (it autostarts) within parse_timeout.
                    allow_browser=False,
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

    # Score sources with the CPU decoder and stash decoder_score on each; returns the
    # blend weight actually used (0 when the decoder is disabled, absent, or failed).
    def _decoder_rerank(self, query: str, sources: dict[str, "_Source"]) -> float:
        if not sources:
            return 0.0
        from core.config import load_search_config

        models_cfg = load_search_config().models
        if not models_cfg.enable_decoder:
            return 0.0
        from core.search.decoder_ranker import get_decoder_ranker

        ranker = get_decoder_ranker()
        if not ranker.available():
            return 0.0
        items = list(sources.values())
        candidates = [
            {"title": s.title, "url": s.url, "snippet": s.snippet, "preview": s.parsed_markdown[:2000]}
            for s in items
        ]
        scores = ranker.score(query, candidates)
        if len(scores) != len(items):
            return 0.0
        for source, score in zip(items, scores):
            source.decoder_score = max(0.0, min(1.0, score))
        logger.info("decoder.rerank scored=%d query=%r", len(items), query[:120])
        return max(0.0, min(1.0, float(models_cfg.decoder_weight)))

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
            # Snippet-only sources (read_page-only handler / learned-slow domain) never
            # spend a parse slot — they stay in the ranked output without a page fetch.
            if not _inline_parse_allowed(url):
                trace_logger.info("parse.skip host=%s url=%r (snippet-only)", source.host, url)
                return
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
            # read_page; the warm browser runs out-of-process in its own daemon.
            pending = [task for task in parse_tasks.values() if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        # High-effort content-stage re-rank: blend the rules score with a CPU decoder
        # relevance score over (query, title, url, snippet, parsed preview). No-op when
        # the decoder is off/absent — the rules ranking stays in charge.
        decoder_weight = self._decoder_rerank(query, sources) if profile.allow_decoder else 0.0

        def _final_score(s: _Source) -> float:
            if s.decoder_score < 0 or decoder_weight <= 0:
                return s.score
            return (1.0 - decoder_weight) * s.score + decoder_weight * s.decoder_score

        ranked = sorted(sources.values(), key=_final_score, reverse=True)
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
                    **({"decoder_score": round(s.decoder_score, 4)} if s.decoder_score >= 0 else {}),
                    **({"pdf_url": pdf} if (pdf := _infer_pdf_url(s.url)) else {}),
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


# Build the payload returned when an identical query is hard-blocked as a repeat.
def _repeat_block_payload(query: str, effort: str, age: float) -> dict[str, Any]:
    return {
        "query": query,
        "effort": effort,
        "blocked": True,
        "block_reason": "repeat",
        "note": (
            f"You already ran this exact search {age:.0f}s ago — the results were just "
            "shown above. Re-issuing the same query is suppressed; reuse the previous "
            "results, refine the query, or read_page one of those sources."
        ),
        "sources": [],
    }


# Cached/blocked/deduped entry point used by the MCP tool (run_web_search).
#
# Wraps the pure WebSearchService.search with the short-horizon "search memory":
#   1. identical query within the block window → hard block (no engines hit);
#   2. otherwise serve from the query-results cache when fresh, else run live;
#   3. drop result URLs already shown to the model within the suppression window;
#   4. record what was served, then warm the top unparsed URLs in the background.
async def run_web_search(
    query: str,
    *,
    effort: str = "low",
    region: str = "",
    safesearch: str = "moderate",
    timelimit: str | None = None,
) -> dict[str, Any]:
    from core.cache.hosted_cache import get_hosted_cache
    from core.config import load_search_config

    from .prefetch import get_prefetch_manager
    from .recent_tracker import get_recent_tracker

    cache_cfg = load_search_config().cache
    tracker = get_recent_tracker()
    cache = get_hosted_cache()
    key_args = dict(region=region, safesearch=safesearch, timelimit=timelimit, effort=effort)
    qkey = tracker.query_key(query, **key_args)

    # 1. Identical query just served → hard block, no engines.
    age = tracker.repeat_age(qkey, cache_cfg.repeat_block_window_seconds)
    if age is not None:
        logger.info("web_search.repeat_block age=%.0fs query=%r", age, query[:160])
        return _repeat_block_payload(query, effort, age)

    # 2. Fresh cache hit, else run the live pipeline and cache it.
    payload = cache.get(query, **key_args)
    if payload is not None:
        payload = {**payload, "cached": True}
    else:
        payload = await WebSearchService().search(
            query, effort=effort, region=region, safesearch=safesearch, timelimit=timelimit
        )
        payload["cached"] = False
        cache.set(query, payload, is_empty=not payload.get("sources"), **key_args)

    # 3. Drop sources the model was already shown within the suppression window.
    sources = list(payload.get("sources") or [])
    seen = tracker.recently_seen(
        [s.get("url", "") for s in sources], cache_cfg.seen_source_window_seconds
    )
    if seen:
        kept = [s for s in sources if s.get("url") not in seen]
        payload = {**payload, "sources": kept, "suppressed_seen": len(seen)}
        sources = kept

    # 4. Remember what we served, then warm the top unparsed URLs for likely read_page.
    served_urls = [s.get("url", "") for s in sources]
    horizon = max(cache_cfg.repeat_block_window_seconds, cache_cfg.seen_source_window_seconds, 60)
    tracker.record(qkey, served_urls, horizon=float(horizon))

    if cache_cfg.prefetch_max_urls > 0:
        targets = [s.get("url", "") for s in sources if not s.get("markdown")]
        get_prefetch_manager().schedule(targets[: cache_cfg.prefetch_max_urls])

    return payload
