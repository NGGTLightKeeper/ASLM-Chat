"""Deterministic SERP triage owned by the search core."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse

from core.models.search import SearchResult
from core.query.routing_score import QueryClassWeight, compute_routing_score
from core.registry.domain_reputation import domain_from_url, get_reputation_store
from core.registry.trust_registry import get_trust_registry

logger = logging.getLogger(__name__)

TIER_TRUST_SCORES = {
    "A": 1.0,
    "B": 0.75,
    "C": 0.45,
    "friendly": 1.0,
    "moderate": 0.75,
    "hardened": 0.35,
    "fortress": 0.05,
    "?": 0.50,
    "unknown": 0.50,
}

_SKIP_TITLE_PATTERNS = frozenset({
    "login", "log in", "sign up", "signup", "sign in", "register",
    "create account", "subscribe", "404", "403", "not found",
    "access denied", "page not found", "permission denied",
})
_DATE_SIGNAL_RE = re.compile(
    r"\b(20\d{2}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
    re.IGNORECASE,
)
_HUB_URL_SEGMENTS = frozenset({
    "category", "categories", "tag", "tags", "topic", "topics",
    "theme", "themes", "rubric", "rubrics", "section", "sections",
    "label", "labels", "archive", "archives", "feed", "rss",
    "search", "results", "page", "index", "catalog",
})
_HUB_TITLE_PHRASES = (
    "all news", "all articles", "all posts", "news feed", "tag page",
    "category page", "topic page", "browse", "archive",
    "\u0432\u0441\u0435 \u043d\u043e\u0432\u043e\u0441\u0442\u0438",
    "\u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u043d\u043e\u0432\u043e\u0441\u0442\u0438",
    "\u0432\u0441\u0435 \u0441\u0442\u0430\u0442\u044c\u0438",
)


@dataclass
class TriageResult:
    skip: bool
    fetch_policy: str
    score: float


class TriageSession:
    """Incrementally rank candidates as engines produce them."""

    def __init__(self, query: str, class_mix: list[QueryClassWeight], *, expected_total: int = 10) -> None:
        self.query = query
        self.class_mix = class_mix
        self.expected_total = max(1, expected_total)
        self.seen = 0
        try:
            self.trust_reg = get_trust_registry()
        except Exception:  # noqa: BLE001
            self.trust_reg = None
        try:
            self.rep_store = get_reputation_store()
        except Exception:  # noqa: BLE001
            self.rep_store = None

    def ingest(
        self,
        result: SearchResult,
        *,
        decoder_score: float | None = None,
        decoder_debug: Any = None,
    ) -> TriageResult:
        apply_registry_routing([result], self.class_mix)
        if decoder_score is not None:
            apply_candidate_scores(
                [result],
                [decoder_score],
                debug_key="snippet_decoder_top" if decoder_debug is not None else None,
                debug_values=[decoder_debug] if decoder_debug is not None else None,
            )
        decision = triage_one_result(
            result,
            self.query,
            index=self.seen,
            total=max(self.expected_total, self.seen + 1),
            trust_reg=self.trust_reg,
            rep_store=self.rep_store,
        )
        self.seen += 1
        return decision


def _hub_penalty(url: str, title: str, snippet: str) -> float:
    penalty = 0.0
    path = (urlparse(url).path or "").lower().strip("/")
    if set(path.split("/")) & _HUB_URL_SEGMENTS:
        penalty += 0.5
    if not path or path in {"index", "index.html", "index.php"}:
        penalty += 0.3
    if any(phrase in (title or "").lower() for phrase in _HUB_TITLE_PHRASES):
        penalty += 0.4
    snippet = snippet or ""
    if snippet.count(" | ") >= 4 or snippet.count(" \u00b7 ") >= 3 or snippet.count(" \u2022 ") >= 3:
        penalty += 0.25
    return min(penalty, 1.0)


def resolve_result_trust_tier(result: SearchResult, url: str, *, trust_reg, rep_store) -> None:
    if (result.trust_tier or "?") != "?":
        return
    if trust_reg is not None:
        tier = trust_reg.get_tier(url)
        if tier:
            result.trust_tier = tier
            return
    if rep_store is not None:
        try:
            promoted = rep_store.get_promoted_tier(domain_from_url(url))
            if promoted in {"B", "C"}:
                result.trust_tier = promoted
        except Exception as exc:  # noqa: BLE001
            logger.debug("rep_store.get_promoted_tier failed for %s: %s", url, exc)


def apply_registry_routing(results: list[SearchResult], class_mix: list[QueryClassWeight]) -> None:
    for result in results:
        try:
            routing = compute_routing_score(result.url, class_mix)
            result.routing_score = routing.multiplier
            result.routing_debug = routing.debug
        except Exception as exc:  # noqa: BLE001
            logger.debug("routing_score failed url=%s: %s", result.url, exc)
            result.routing_score = 1.0
            result.routing_debug = {}


def apply_candidate_scores(
    results: Iterable[SearchResult],
    scores: Iterable[float],
    *,
    field: str = "snippet_relevance_score",
    debug_key: str | None = None,
    debug_values: Iterable[Any] | None = None,
) -> list[float]:
    """Attach optional model scores without making search core own model runtime."""
    normalized: list[float] = []
    debug_items = iter(debug_values) if debug_values is not None else None
    for result, raw_score in zip(results, scores, strict=False):
        score = max(0.0, min(1.0, float(raw_score or 0.0)))
        setattr(result, field, score)
        normalized.append(score)
        if debug_key and debug_items is not None:
            result.routing_debug = dict(result.routing_debug or {})
            result.routing_debug[debug_key] = next(debug_items, None)
    return normalized


def triage_soft_score(result: SearchResult, query: str, *, index: int, total: int) -> float:
    from core.extract.scoring import lexical_score

    title = (result.title or "").strip()
    snippet = (result.snippet or "").strip()
    pos_score = 1.0 - (index / max(total - 1, 1))
    snip_score = min(1.0, len(snippet) / 300)
    lex = lexical_score(query, title, snippet, result.url)
    tier_trust = TIER_TRUST_SCORES.get(result.trust_tier or "unknown", 0.5)
    date_boost = 0.08 if _DATE_SIGNAL_RE.search(snippet) else 0.0
    hub_penalty = _hub_penalty(result.url, title, snippet)
    routing = max(0.45, min(1.65, float(result.routing_score or 1.0)))
    snippet_rel = max(0.0, min(1.0, float(result.snippet_relevance_score or 0.0)))
    score = (
        0.25 * pos_score
        + 0.10 * snip_score
        + 0.40 * lex
        + 0.15 * tier_trust
        + 0.10 * snippet_rel
        + 0.08 * ((routing - 1.0) / 0.65)
        + date_boost
        - 0.20 * hub_penalty
    )
    return max(0.0, min(1.0, score))


def triage_one_result(
    result: SearchResult,
    query: str,
    *,
    index: int,
    total: int,
    trust_reg=None,
    rep_store=None,
) -> TriageResult:
    title = (result.title or "").strip()
    snippet = (result.snippet or "").strip()
    resolve_result_trust_tier(result, result.url, trust_reg=trust_reg, rep_store=rep_store)
    if len(snippet) < 30 or (len(snippet) < 60 and len(title) < 20):
        return TriageResult(skip=True, fetch_policy="cheap", score=0.0)
    if any(pattern in title.lower() for pattern in _SKIP_TITLE_PATTERNS):
        return TriageResult(skip=True, fetch_policy="cheap", score=0.0)
    try:
        if trust_reg is not None and trust_reg.is_blacklisted(result.url):
            return TriageResult(skip=True, fetch_policy="cheap", score=0.0)
        if rep_store is not None and rep_store.is_auto_blacklisted(domain_from_url(result.url)):
            return TriageResult(skip=True, fetch_policy="cheap", score=0.0)
    except Exception as exc:  # noqa: BLE001
        logger.debug("triage registry lookup failed for %s: %s", result.url, exc)
    score = triage_soft_score(result, query, index=index, total=total)
    if score < 0.10:
        return TriageResult(skip=True, fetch_policy="cheap", score=score)
    return TriageResult(skip=False, fetch_policy="race" if score >= 0.50 else "cheap", score=score)


def triage_results(results: list[SearchResult], query: str) -> list[TriageResult]:
    try:
        trust_reg = get_trust_registry()
    except Exception as exc:  # noqa: BLE001
        logger.debug("trust_registry unavailable: %s", exc)
        trust_reg = None
    try:
        rep_store = get_reputation_store()
    except Exception as exc:  # noqa: BLE001
        logger.debug("reputation_store unavailable: %s", exc)
        rep_store = None
    return [
        triage_one_result(result, query, index=index, total=len(results), trust_reg=trust_reg, rep_store=rep_store)
        for index, result in enumerate(results)
    ]
