# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Profile-aware chunk selection and SEO keyword-stuffing penalties for previews."""

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

# Output-profile families (aligned with services.web_search._OUTPUT_PROFILES).
_DEPTH_FIRST_TYPES = frozenset({"technical", "academic", "medical", "troubleshooting"})
_BREADTH_FIRST_TYPES = frozenset({"journalistic", "forum", "shopping"})


@dataclass(frozen=True)
class ChunkCompressPolicy:
    """How aggressively to keep scored paragraphs for a query class."""

    char_budget: int
    # Minimum hybrid score (0..1) for a paragraph to be eligible.
    min_score: float
    # Hard cap on paragraph count in the output.
    max_chunks: int
    # When many paragraphs pass min_score, allow up to this many chunks.
    max_chunks_expanded: int
    # Score needed to count toward "many good chunks" expansion.
    expand_score: float
    # Weight of SEO stuffing penalty in the hybrid score.
    seo_weight: float = 0.45


_POLICIES: dict[str, ChunkCompressPolicy] = {
    # Few, high-precision fragments unless many strong chunks exist.
    "general": ChunkCompressPolicy(
        char_budget=1_400,
        min_score=0.40,
        max_chunks=4,
        max_chunks_expanded=8,
        expand_score=0.52,
    ),
    "finance": ChunkCompressPolicy(
        char_budget=1_500,
        min_score=0.38,
        max_chunks=5,
        max_chunks_expanded=9,
        expand_score=0.50,
    ),
    # Volume-first: tight cap on parsed depth per source.
    "journalistic": ChunkCompressPolicy(
        char_budget=1_000,
        min_score=0.44,
        max_chunks=3,
        max_chunks_expanded=5,
        expand_score=0.56,
        seo_weight=0.50,
    ),
    "forum": ChunkCompressPolicy(
        char_budget=1_100,
        min_score=0.42,
        max_chunks=3,
        max_chunks_expanded=5,
        expand_score=0.54,
    ),
    "shopping": ChunkCompressPolicy(
        char_budget=1_200,
        min_score=0.41,
        max_chunks=4,
        max_chunks_expanded=6,
        expand_score=0.52,
    ),
    # Depth-first: more room, lower bar, more chunks when signal is strong.
    "technical": ChunkCompressPolicy(
        char_budget=2_400,
        min_score=0.30,
        max_chunks=10,
        max_chunks_expanded=14,
        expand_score=0.40,
        seo_weight=0.40,
    ),
    "academic": ChunkCompressPolicy(
        char_budget=2_200,
        min_score=0.32,
        max_chunks=9,
        max_chunks_expanded=13,
        expand_score=0.42,
    ),
    "medical": ChunkCompressPolicy(
        char_budget=2_300,
        min_score=0.30,
        max_chunks=10,
        max_chunks_expanded=14,
        expand_score=0.40,
    ),
    "troubleshooting": ChunkCompressPolicy(
        char_budget=2_400,
        min_score=0.28,
        max_chunks=11,
        max_chunks_expanded=15,
        expand_score=0.38,
    ),
}

_DEFAULT_POLICY = _POLICIES["general"]

def policy_family(query_type: str | None) -> str:
    """Map query class to breadth / general / depth chunk family."""
    key = (query_type or "general").strip().lower()
    if key in _DEPTH_FIRST_TYPES:
        return "depth"
    if key in _BREADTH_FIRST_TYPES:
        return "breadth"
    if key in _POLICIES:
        if key in {"technical", "academic", "medical", "troubleshooting"}:
            return "depth"
        if key in {"journalistic", "forum", "shopping"}:
            return "breadth"
        return "general"
    return "general"


def resolve_chunk_policy(query_type: str | None, *, char_budget: int | None = None) -> ChunkCompressPolicy:
    """Map primary query class to chunk selection policy."""
    key = (query_type or "general").strip().lower()
    if key not in _POLICIES:
        if key in _DEPTH_FIRST_TYPES:
            key = "technical"
        elif key in _BREADTH_FIRST_TYPES:
            key = "journalistic"
        else:
            key = "general"
    policy = _POLICIES.get(key, _DEFAULT_POLICY)
    if char_budget is None or char_budget <= 0:
        return policy
    scale = max(0.5, min(3.0, char_budget / max(1, policy.char_budget)))
    return ChunkCompressPolicy(
        char_budget=max(400, int(policy.char_budget * scale)),
        min_score=policy.min_score,
        max_chunks=policy.max_chunks,
        max_chunks_expanded=policy.max_chunks_expanded,
        expand_score=policy.expand_score,
        seo_weight=policy.seo_weight,
    )


def _tokenize(text: str) -> list[str]:
    return _bm25_tokenize(text)


def _sentence_like_ratio(text: str) -> float:
    compact = (text or "").strip()
    if len(compact) < 40:
        return 0.0
    endings = len(re.findall(r"[.!?…]", compact))
  # Lists/tables may have few sentence ends — do not over-penalize.
    return min(1.0, endings / max(1, len(compact) / 180))


def _entity_heuristic_score(text: str) -> float:
    """Cheap factual-density proxy without GLiNER (0..1)."""
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    unique_ratio = len(set(tokens)) / len(tokens)
    digit_hits = sum(1 for ch in text if ch.isdigit())
    currency_hit = has_currency(text)
    unit_hit = has_measurement(text)
    score = 0.0
    score += min(0.35, unique_ratio * 0.5)
    score += 0.15 if digit_hits >= 2 else 0.05 if digit_hits else 0.0
    score += 0.20 if currency_hit else 0.0
    score += 0.10 if unit_hit else 0.0
    score += 0.20 * _sentence_like_ratio(text)
    return min(1.0, score)


def _normalize_scores(values: list[float]) -> list[float]:
    if not values:
        return []
    peak = max(values)
    if peak <= 0:
        return [0.0] * len(values)
    return [min(1.0, max(0.0, v / peak)) for v in values]


def _score_paragraphs(
    paragraphs: list[str],
    query_terms: list[str],
    policy: ChunkCompressPolicy,
) -> list[tuple[float, float]]:
    """Return (hybrid_score, seo_penalty) per paragraph."""
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


def _chunk_limit(policy: ChunkCompressPolicy, strong_count: int) -> int:
    if strong_count >= policy.max_chunks and strong_count >= 3:
        return policy.max_chunks_expanded
    return policy.max_chunks


def compress_chunks_profiled(
    text: str,
    query: str,
    *,
    query_type: str | None = None,
    char_budget: int | None = None,
) -> tuple[str, dict[str, object]]:
    """Select paragraphs by relevance + entity heuristics; penalize SEO stuffing.

    Returns (compressed_text, debug_info).
    """
    policy = resolve_chunk_policy(query_type, char_budget=char_budget)
    fam = policy_family(query_type)
    debug: dict[str, object] = {
        "policy": query_type or "general",
        "policy_family": fam,
        "char_budget": policy.char_budget,
    }

    paragraphs = _split_blocks(text)
    if not paragraphs:
        trimmed = _truncate_at_sentence(text[: policy.char_budget], policy.char_budget)
        debug["strategy"] = "truncate_only"
        return trimmed, debug

    query_terms = _bm25_tokenize(query)

    scored = _score_paragraphs(paragraphs, query_terms, policy)

    if len(text) <= policy.char_budget:
        kept: list[int] = []
        rejected_seo = 0
        for idx, ((hybrid, seo), _para) in enumerate(zip(scored, paragraphs)):
            if seo >= SEO_HARD_REJECT_THRESHOLD:
                rejected_seo += 1
                continue
            if hybrid >= policy.min_score:
                kept.append(idx)
        debug["rejected_seo"] = rejected_seo
        debug["strategy"] = "passthrough_filtered"
        if kept:
            joined = "\n\n".join(paragraphs[i] for i in sorted(kept))
            debug["chunks_selected"] = len(kept)
            return joined, debug
        debug["strategy"] = "passthrough_empty_after_seo"
        return "", debug

    eligible: list[tuple[int, float, float]] = []
    rejected_seo = 0
    for idx, ((hybrid, seo), para) in enumerate(zip(scored, paragraphs)):
        if seo >= SEO_HARD_REJECT_THRESHOLD:
            rejected_seo += 1
            continue
        if hybrid < policy.min_score:
            continue
        eligible.append((idx, hybrid, seo))

    debug["rejected_seo"] = rejected_seo
    debug["eligible"] = len(eligible)

    if not eligible:
        # Fallback: least-spammy paragraphs by BM25 only.
        ranked = sorted(
            range(len(paragraphs)),
            key=lambda i: (-scored[i][0], scored[i][1]),
        )
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
        debug["strategy"] = "fallback_bm25"
    else:
        strong = [item for item in eligible if item[1] >= policy.expand_score]
        chunk_cap = _chunk_limit(policy, len(strong))
        ranked = sorted(eligible, key=lambda x: -x[1])
        selected_idx_set: set[int] = set()
        budget = policy.char_budget
        for idx, hybrid, _seo in ranked:
            if len(selected_idx_set) >= chunk_cap:
                break
            cost = len(paragraphs[idx]) + 2
            if cost <= budget:
                selected_idx_set.add(idx)
                budget -= cost
        selected_idx = sorted(selected_idx_set)
        debug["strategy"] = "profiled"
        debug["chunk_cap"] = chunk_cap

    if not selected_idx:
        trimmed = _truncate_at_sentence(text[: policy.char_budget], policy.char_budget)
        debug["strategy"] = "truncate_empty"
        return trimmed, debug

    joined = "\n\n".join(paragraphs[i] for i in selected_idx)
    if len(joined) > policy.char_budget:
        joined = _truncate_at_sentence(joined, policy.char_budget)
    debug["output_chars"] = len(joined)
    debug["chunks_selected"] = len(selected_idx)
    return joined, debug
