# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Query-relevant chunk compaction for parsed-page content.

One consistent algorithm: score paragraphs by BM25 relevance to the query + a cheap
factual-density heuristic, reject SEO-stuffed blocks, and pack the best into a character
budget. No per-type "profiles" or query classification — the previous taxonomy only
swapped numeric constants and routed to behaviour that never existed; a single policy
(budget-scalable) is the honest shape. No models, no embeddings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.extract.chunk_quality import (
    SEO_HARD_REJECT_THRESHOLD,
    seo_keyword_stuffing_penalty,
)
from core.extract.fact_signals import has_currency, has_measurement
from core.extract.content_processor import (
    _bm25_score_paragraphs,
    _bm25_tokenize,
    _clean_latex_for_index,
    _has_latex,
    _split_blocks,
    _truncate_at_sentence,
)


@dataclass(frozen=True)
class _Policy:
    char_budget: int = 1_400
    min_score: float = 0.40
    max_chunks: int = 4
    max_chunks_expanded: int = 8
    expand_score: float = 0.52
    seo_weight: float = 0.45


_DEFAULT_POLICY = _Policy()


# The single compaction policy, optionally rescaled to a caller's char budget.
def _policy_for(char_budget: int | None) -> _Policy:
    if char_budget is None or char_budget <= 0:
        return _DEFAULT_POLICY
    scale = max(0.5, min(3.0, char_budget / _DEFAULT_POLICY.char_budget))
    return _Policy(
        char_budget=max(400, int(_DEFAULT_POLICY.char_budget * scale)),
        min_score=_DEFAULT_POLICY.min_score,
        max_chunks=_DEFAULT_POLICY.max_chunks,
        max_chunks_expanded=_DEFAULT_POLICY.max_chunks_expanded,
        expand_score=_DEFAULT_POLICY.expand_score,
        seo_weight=_DEFAULT_POLICY.seo_weight,
    )


# Fraction of text that looks like complete sentences.
def _sentence_like_ratio(text: str) -> float:
    compact = (text or "").strip()
    if len(compact) < 40:
        return 0.0
    endings = len(re.findall(r"[.!?…]", compact))
    return min(1.0, endings / max(1, len(compact) / 180))


# Cheap factual-density proxy without GLiNER (0..1).
def _entity_heuristic_score(text: str) -> float:
    tokens = _bm25_tokenize(text)
    if not tokens:
        return 0.0
    unique_ratio = len(set(tokens)) / len(tokens)
    digit_hits = sum(1 for ch in text if ch.isdigit())
    score = 0.0
    score += min(0.35, unique_ratio * 0.5)
    score += 0.15 if digit_hits >= 2 else 0.05 if digit_hits else 0.0
    score += 0.20 if has_currency(text) else 0.0
    score += 0.10 if has_measurement(text) else 0.0
    score += 0.20 * _sentence_like_ratio(text)
    return min(1.0, score)


# Scale scores to [0, 1] by peak value.
def _normalize_scores(values: list[float]) -> list[float]:
    if not values:
        return []
    peak = max(values)
    if peak <= 0:
        return [0.0] * len(values)
    return [min(1.0, max(0.0, v / peak)) for v in values]


# Return (hybrid_score, seo_penalty) per paragraph.
def _score_paragraphs(
    paragraphs: list[str], query_terms: list[str], policy: _Policy
) -> list[tuple[float, float]]:
    if not paragraphs:
        return []

    if _has_latex("\n\n".join(paragraphs)):
        index_paras = [_clean_latex_for_index(p) for p in paragraphs]
    else:
        index_paras = paragraphs

    bm25_raw = _bm25_score_paragraphs(index_paras, query_terms) if query_terms else [0.0] * len(paragraphs)
    bm25 = _normalize_scores(bm25_raw)
    entity = [_entity_heuristic_score(p) for p in paragraphs]
    seo = [seo_keyword_stuffing_penalty(p, query_terms) for p in paragraphs]

    seo_w = max(0.0, min(1.0, policy.seo_weight))
    remainder = max(0.05, 1.0 - seo_w)
    bm25_w = remainder * (0.55 / 0.80)
    entity_w = remainder * (0.25 / 0.80)

    scored: list[tuple[float, float]] = []
    for b, e, s in zip(bm25, entity, seo):
        hybrid = bm25_w * b + entity_w * e + seo_w * (1.0 - s)
        scored.append((min(1.0, hybrid), s))
    return scored


# Cap on paragraph count; expands when many strong chunks exist.
def _chunk_limit(policy: _Policy, strong_count: int) -> int:
    if strong_count >= policy.max_chunks and strong_count >= 3:
        return policy.max_chunks_expanded
    return policy.max_chunks


# Select the paragraphs most relevant to the query, dropping SEO-stuffed blocks, and
# pack them into the (optionally rescaled) character budget. Returns the joined text.
def compress_chunks(text: str, query: str, *, char_budget: int | None = None) -> str:
    policy = _policy_for(char_budget)

    paragraphs = _split_blocks(text)
    if not paragraphs:
        return _truncate_at_sentence(text[: policy.char_budget], policy.char_budget)

    query_terms = _bm25_tokenize(query)
    scored = _score_paragraphs(paragraphs, query_terms, policy)

    if len(text) <= policy.char_budget:
        kept = [
            idx
            for idx, ((hybrid, seo), _para) in enumerate(zip(scored, paragraphs))
            if seo < SEO_HARD_REJECT_THRESHOLD and hybrid >= policy.min_score
        ]
        if kept:
            return "\n\n".join(paragraphs[i] for i in sorted(kept))
        return ""

    eligible: list[tuple[int, float, float]] = []
    for idx, ((hybrid, seo), _para) in enumerate(zip(scored, paragraphs)):
        if seo >= SEO_HARD_REJECT_THRESHOLD or hybrid < policy.min_score:
            continue
        eligible.append((idx, hybrid, seo))

    if not eligible:
        # Fallback: least-spammy paragraphs by score only.
        ranked = sorted(range(len(paragraphs)), key=lambda i: (-scored[i][0], scored[i][1]))
        fallback: list[int] = []
        budget = policy.char_budget
        for idx in ranked:
            if scored[idx][1] >= 0.92:
                continue
            cost = len(paragraphs[idx]) + 2
            if cost <= budget:
                fallback.append(idx)
                budget -= cost
            if len(fallback) >= policy.max_chunks:
                break
        selected_idx = sorted(fallback)
    else:
        strong = [item for item in eligible if item[1] >= policy.expand_score]
        chunk_cap = _chunk_limit(policy, len(strong))
        ranked = sorted(eligible, key=lambda x: -x[1])
        selected: set[int] = set()
        budget = policy.char_budget
        for idx, _hybrid, _seo in ranked:
            if len(selected) >= chunk_cap:
                break
            cost = len(paragraphs[idx]) + 2
            if cost <= budget:
                selected.add(idx)
                budget -= cost
        selected_idx = sorted(selected)

    if not selected_idx:
        return _truncate_at_sentence(text[: policy.char_budget], policy.char_budget)

    joined = "\n\n".join(paragraphs[i] for i in selected_idx)
    if len(joined) > policy.char_budget:
        joined = _truncate_at_sentence(joined, policy.char_budget)
    return joined
