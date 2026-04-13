# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Deduplication and filtering for full-content deep research sources."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from typing import Dict, List

from services.deep_research.models import ExtractedSource, PhaseResult, ResearchState


# ---------------------------------------------------------------------------
# Clickbait / low-quality title heuristics
# ---------------------------------------------------------------------------

# Each pattern is compiled once.  A title matching ≥1 pattern is "soft clickbait"
# (score × 0.55); ≥2 patterns is "hard clickbait" (score × 0.30).
#
# Conservative by design: only patterns that are EXCLUSIVE to clickbait/aggregator
# content and will not fire on legitimate research, documentation, or news titles.
# When in doubt, a pattern is left out — false positives cost more than false negatives.
_CLICKBAIT_PATTERNS: list[re.Pattern] = [p for p in [re.compile(r, re.IGNORECASE) for r in [
    # "top N" / "top-N" — numbered aggregator lists; almost never in real research
    # Note: "top-k" is safe — \d+ won't match a letter.
    r"\btop[\s\-]+\d+\b",
    # "N tips/tricks/hacks/secrets" — only in how-to clickbait
    r"\b\d+\s+(tips?|tricks?|hacks?|secrets?)\b",
    # Explicit aggregator labels
    r"\b(roundup|listicle)\b",
    # Pure hyperbole — won't appear in academic/official titles
    r"\byou\s+won.t\s+believe\b",
    r"\b(mind.?blowing|life.?changing|game.?changer)\b",
    # "boost/skyrocket your productivity/workflow" — personal productivity bait
    r"\b(boost|skyrocket|supercharge)\s+your\s+(productivity|workflow|output)\b",
    # Russian: "топ N"
    r"\bтоп\s*[-–]?\s*\d+\b",
    # Russian: "N хаков/секретов/лайфхаков"
    r"\b\d+\s+(хаков?|секретов|лайфхаков?)\b",
]]]


def _clickbait_penalty(title: str) -> float:
    """Return a relevance score multiplier based on clickbait signals in the title.

    0 signals  → 1.00 (no penalty)
    1 signal   → 0.55
    2+ signals → 0.30
    """
    if not title or not title.strip():
        return 1.0
    hits = sum(1 for p in _CLICKBAIT_PATTERNS if p.search(title))
    if hits == 0:
        return 1.0
    if hits == 1:
        return 0.55
    return 0.30


def _triage_penalty(src: ExtractedSource) -> float:
    """Return a relevance score multiplier based on triage-assigned metadata.

    Triage already did the heavy lifting (LLM read the content).  Here we
    convert those labels into a score penalty so low-signal sources sink to
    the bottom and are dropped first when the source cap is applied.

    Multipliers are conservative and stacked multiplicatively:
      forum alone          → × 0.75  (StackOverflow can be valuable)
      aggregator alone     → × 0.55  (link-farm / curated list)
      anecdotal alone      → × 0.60  (thin evidence, but might be only source)
      forum + anecdotal    → × 0.30  (random opinion, no evidence)
      aggregator + anecdotal → × 0.25 (worst case: link-farm with no substance)
    """
    ct = (src.content_type or "").strip().lower()
    sc = (src.source_character or "").strip().lower()
    es = (src.evidence_strength or "").strip().lower()

    multiplier = 1.0
    if ct == "forum":
        multiplier *= 0.75
    if sc == "aggregator":
        multiplier *= 0.55
    if es == "anecdotal":
        multiplier *= 0.60
    return multiplier


def _gliner_cuda_enabled(state: ResearchState) -> bool:
    from core.extract.gliner_wrapper import gliner_cuda_enabled
    return gliner_cuda_enabled(state.log)


async def run_dedup_filter(state: ResearchState) -> PhaseResult:
    """Phase 4: deduplicate and filter extracted sources."""
    t0 = time.time()
    cfg = state.config
    sources = list(state.extracted_sources)
    initial = len(sources)

    if not sources:
        state.log("Dedup: no sources to filter")
        if "dedup_filter" not in state.completed_phases:
            state.completed_phases.append("dedup_filter")
        return PhaseResult(phase_name="dedup_filter", items_produced=0, duration_sec=0.0)

    state.log(f"Dedup: starting with {initial} sources")
    min_keep = min(cfg.dedup_min_sources, initial)

    seen_urls: set[str] = set()
    url_deduped: List[ExtractedSource] = []
    for src in sources:
        url_key = src.url.rstrip("/").lower()
        if url_key not in seen_urls:
            seen_urls.add(url_key)
            url_deduped.append(src)
    if len(url_deduped) < initial:
        state.log(f"  URL dedup: {initial} -> {len(url_deduped)}")
    sources = url_deduped

    try:
        from core.extract.semantic_dedup import minhash_dedup

        before = len(sources)
        deduped = minhash_dedup(
            sources,
            text_fn=lambda s: s.text,
            threshold=cfg.minhash_threshold,
        )
        sources = deduped if len(deduped) >= min_keep else sources[:min_keep]
        if len(sources) < before:
            state.log(f"  MinHash dedup: {before} -> {len(sources)}")
    except Exception as exc:
        state.log(f"  MinHash dedup skipped: {exc}")

    if cfg.use_embeddings and len(sources) > 1:
        try:
            from core.extract.semantic_dedup import embedding_dedup

            before = len(sources)
            deduped = embedding_dedup(
                sources,
                text_fn=lambda s: s.text,
                threshold=cfg.embedding_threshold,
            )
            sources = deduped if len(deduped) >= min_keep else sources[:min_keep]
            if len(sources) < before:
                state.log(f"  Embedding dedup: {before} -> {len(sources)}")
        except Exception as exc:
            state.log(f"  Embedding dedup skipped: {exc}")

    if cfg.use_gliner and cfg.depth in ("high", "extra") and sources and _gliner_cuda_enabled(state):
        try:
            from core.extract.gliner_wrapper import (
                check_information_density,
                detect_language_and_adjust_threshold,
                get_labels_for_query,
            )

            labels = get_labels_for_query(state.question, state.query_type)
            before = len(sources)
            filtered: List[ExtractedSource] = []
            for src in sources:
                threshold = detect_language_and_adjust_threshold(src.text[:500])
                passes, _ = check_information_density(
                    src.text,
                    labels,
                    min_entities=cfg.min_entity_density,
                    threshold=threshold,
                    device="cuda",
                )
                if passes:
                    filtered.append(src)
            if len(filtered) < before:
                state.log(f"  GLiNER density filter: {before} -> {len(filtered)}")
            sources = filtered if len(filtered) >= min_keep else sources[:min_keep]
        except Exception as exc:
            state.log(f"  GLiNER filter skipped: {exc}")

    if cfg.depth in ("low", "medium"):
        before = len(sources)
        sources = [src for src in sources if src.evidence_strength != "anecdotal"]
        if not sources:
            sources = url_deduped[: cfg.max_sources]
        if len(sources) < before:
            state.log(f"  Anecdotal filter: {before} -> {len(sources)}")

    # Quality penalty pass — applied to all depths.
    # Combines clickbait title heuristics with triage-assigned metadata labels.
    # Both multipliers stack: a listicle forum post with an anecdotal evidence
    # rating can end up near 0 and will be dropped at the source cap.
    cb_penalized = triage_penalized = 0
    for src in sources:
        m = _clickbait_penalty(src.title)
        t = _triage_penalty(src)
        combined = m * t
        if combined < 1.0:
            src.relevance_score = (src.relevance_score or 0.0) * combined
            if m < 1.0:
                cb_penalized += 1
            if t < 1.0:
                triage_penalized += 1
    if cb_penalized:
        state.log(f"  Clickbait title penalty: {cb_penalized} source(s)")
    if triage_penalized:
        state.log(f"  Triage quality penalty: {triage_penalized} source(s) (forum/aggregator/anecdotal)")

    sources.sort(
        key=lambda src: (
            float(getattr(src, "relevance_score", 0.0) or 0.0),
            int(getattr(src, "char_count", 0) or 0),
        ),
        reverse=True,
    )
    if len(sources) > cfg.max_sources:
        state.log(f"  Source cap: {len(sources)} -> {cfg.max_sources}")
        sources = sources[: cfg.max_sources]

    state.extracted_sources = sources
    clusters: Dict[str, List[int]] = defaultdict(list)
    for index, src in enumerate(sources):
        cluster_key = src.sub_topic.strip().lower() if src.sub_topic else "general"
        clusters[cluster_key].append(index)
    state.log(f"Dedup complete: {initial} -> {len(sources)} sources, {len(clusters)} clusters")

    dt = time.time() - t0
    if "dedup_filter" not in state.completed_phases:
        state.completed_phases.append("dedup_filter")
    return PhaseResult(phase_name="dedup_filter", items_produced=len(sources), duration_sec=dt)
