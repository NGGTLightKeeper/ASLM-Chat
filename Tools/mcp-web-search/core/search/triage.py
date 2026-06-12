# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Incremental, model-free SERP triage.

Sources are scored the moment they arrive from search_stream. The session decides
per source: parse now, hold in queue, or skip. Consensus votes (the same URL
surfacing from another provider family) re-score an already-seen source and may
upgrade it from the queue into a parse slot.

No registries, no models, no I/O — pure functions over SERP fields, so a decision
costs well under a millisecond.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .quality import (
    has_date_signal,
    hub_penalty,
    is_skip_title,
    lexical_score,
    query_years,
    year_match_score,
)

# Engine classes drive how much a SERP position is worth (TODO.md §6/§7):
# premier indexes earn a strong positional prior, recall helpers a weak one.
_ENGINE_POSITION_WEIGHT = {
    "google": 1.00,
    "startpage": 1.00,  # same family, same prior
    "yandex": 0.85,
    "duckduckgo": 0.85,
    "brave": 0.70,
    "qwant": 0.60,
    "yep": 0.50,
}
_DEFAULT_POSITION_WEIGHT = 0.60

# Expected SERP depth used to decay position into [0,1].
_POSITION_DEPTH = 10

# Consensus: votes from distinct provider families. Primary trust signal — it
# replaces the legacy curated trust registry (deleted by design).
_CONSENSUS_STEP = 0.18
_CONSENSUS_CAP = 0.36

# Decision thresholds on the [0,1] soft score.
_SKIP_THRESHOLD = 0.10
_PARSE_THRESHOLD = 0.50

# Snippet shorter than this gets a soft penalty (legacy hard-skipped — too harsh:
# engines legitimately emit short snippets).
_SHORT_SNIPPET_CHARS = 30
_SHORT_SNIPPET_PENALTY = 0.08


class TriageAction(StrEnum):
    PARSE = "parse"  # score cleared the bar — fetch/parse immediately
    QUEUE = "queue"  # usable, waits for a free slot or a consensus upgrade
    SKIP = "skip"  # not worth a fetch


@dataclass(slots=True)
class TriageDecision:
    action: TriageAction
    score: float
    url: str
    # True when this decision upgrades a previously queued source (consensus vote).
    upgraded: bool = False


# Internal per-URL state for incremental consensus rescoring.
@dataclass(slots=True)
class _SourceState:
    base_score: float
    families: set[str] = field(default_factory=set)
    action: TriageAction = TriageAction.SKIP


# Incremental triage over the live source stream.
class TriageSession:

    def __init__(self, query: str) -> None:
        self.query = query
        self._years = query_years(query)
        self._states: dict[str, _SourceState] = {}

    # Score one source from its SERP fields alone (no consensus component).
    def _soft_score(
        self,
        *,
        engine: str,
        rank: int,
        title: str,
        snippet: str,
        url: str,
    ) -> float:
        position = max(0.0, 1.0 - (max(1, rank) - 1) / _POSITION_DEPTH)
        position_weight = _ENGINE_POSITION_WEIGHT.get(engine, _DEFAULT_POSITION_WEIGHT)
        lex = lexical_score(self.query, title, snippet, url)
        hub = hub_penalty(url, title, snippet)
        snip_len = min(1.0, len(snippet) / 300)

        score = (
            0.30 * position * position_weight
            + 0.45 * lex
            + 0.10 * snip_len
        )
        if has_date_signal(snippet):
            score += 0.05
        if self._years:
            score += 0.10 * year_match_score(f"{title} {snippet}", self._years)
        if len(snippet) < _SHORT_SNIPPET_CHARS:
            score -= _SHORT_SNIPPET_PENALTY
        score -= 0.25 * hub
        return max(0.0, min(1.0, score))

    # Map a score to an action.
    @staticmethod
    def _action_for(score: float) -> TriageAction:
        if score < _SKIP_THRESHOLD:
            return TriageAction.SKIP
        return TriageAction.PARSE if score >= _PARSE_THRESHOLD else TriageAction.QUEUE

    # Total score = base soft score + consensus bonus for extra families.
    @staticmethod
    def _total(state: _SourceState) -> float:
        extra_votes = max(0, len(state.families) - 1)
        bonus = min(_CONSENSUS_CAP, extra_votes * _CONSENSUS_STEP)
        return min(1.0, state.base_score + bonus)

    # Ingest a new source event; returns the decision for this URL.
    def ingest_source(
        self,
        *,
        engine: str,
        provider_family: str,
        rank: int,
        url: str,
        title: str,
        snippet: str,
    ) -> TriageDecision:
        if is_skip_title(title):
            self._states[url] = _SourceState(base_score=0.0, action=TriageAction.SKIP)
            return TriageDecision(action=TriageAction.SKIP, score=0.0, url=url)

        base = self._soft_score(engine=engine, rank=rank, title=title, snippet=snippet, url=url)
        state = _SourceState(base_score=base)
        state.families.add(provider_family)
        score = self._total(state)
        state.action = self._action_for(score)
        self._states[url] = state
        return TriageDecision(action=state.action, score=score, url=url)

    # Ingest a consensus vote for an already-seen URL. Returns an upgraded decision
    # when the extra vote lifts the source over a threshold, else None.
    def ingest_vote(self, *, provider_family: str, url: str) -> TriageDecision | None:
        state = self._states.get(url)
        if state is None or state.action == TriageAction.SKIP:
            return None
        if provider_family in state.families:
            return None  # same family re-listing the URL is not new evidence
        state.families.add(provider_family)
        score = self._total(state)
        new_action = self._action_for(score)
        upgraded = new_action == TriageAction.PARSE and state.action == TriageAction.QUEUE
        state.action = new_action
        if upgraded:
            return TriageDecision(action=new_action, score=score, url=url, upgraded=True)
        return None

    # Current score for a URL (queue ordering for leftover slots).
    def score_of(self, url: str) -> float:
        state = self._states.get(url)
        return self._total(state) if state else 0.0
