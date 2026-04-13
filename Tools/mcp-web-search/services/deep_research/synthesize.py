# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Legacy-style final cleanup and hierarchical synthesis."""

from __future__ import annotations

import time
from collections import defaultdict
from math import ceil
from typing import Any

from core.llm.llm_client import call_llm, call_llm_json
from core.llm.tokenizer import count_tokens
from services.deep_research.config import (
    SYNTH_CHAR_BUDGET_PER_SOURCE,
    SYNTH_MAX_TOKENS_MERGE,
    SYNTH_MAX_TOKENS_SINGLE,
)
from services.deep_research.models import ExtractedSource, PhaseResult, ResearchState
from services.deep_research.text_utils import compact_text as _compact_text, sanitize_content as _sanitize_content

# ---------------------------------------------------------------------------
# Context window budget
# Placeholder until ASLM exposes the active model's context size at runtime.
# At that point, replace MODEL_CONTEXT_TOKENS with a config/env lookup.
# CONTEXT_HEADROOM keeps the last N% free for the model's own output.
# ---------------------------------------------------------------------------
MODEL_CONTEXT_TOKENS: int = 72_000
CONTEXT_HEADROOM_RATIO: float = 0.02   # require ≥2% free before output starts


def _source_evidence_brief(source: ExtractedSource, max_chars: int = 420) -> str:
    text = _compact_text(source.summary or source.relevant_chunks or source.text or "")
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "..."
    return text or "(no usable content)"


def _heuristic_final_quality(source: ExtractedSource) -> tuple[float, bool, str]:
    relevance = max(0.0, min(1.0, float(getattr(source, "relevance_score", 0.0) or 0.0)))
    score = relevance * 0.55

    content_type_bonus = {
        "documentation": 0.16,
        "research": 0.14,
        "benchmark": 0.12,
        "tutorial": 0.09,
        "news": 0.05,
        "opinion": -0.02,
        "forum": -0.03,
        "other": 0.0,
    }
    # Fallback to "other" (neutral) when triage hasn't annotated this field yet
    ct_raw = str(getattr(source, "content_type", "") or "").lower().strip()
    ct = ct_raw if ct_raw in content_type_bonus else "other"
    score += content_type_bonus[ct]

    evidence_bonus = {
        "strong": 0.18,
        "moderate": 0.09,
        "weak": -0.02,
        "anecdotal": -0.08,
    }
    # Fallback to "moderate" (neutral positive) when triage hasn't run yet
    es_raw = str(getattr(source, "evidence_strength", "") or "").lower().strip()
    es = es_raw if es_raw in evidence_bonus else "moderate"
    score += evidence_bonus[es]

    character_bonus = {
        "primary": 0.12,
        "secondary": 0.05,
        "aggregator": -0.04,
        "commentary": -0.06,
    }
    # Fallback to "secondary" (neutral positive) when triage hasn't run yet
    sc_raw = str(getattr(source, "source_character", "") or "").lower().strip()
    sc = sc_raw if sc_raw in character_bonus else "secondary"
    score += character_bonus[sc]

    if len(_compact_text(source.relevant_chunks or "")) >= 300:
        score += 0.05
    if len(_compact_text(source.summary or "")) >= 120:
        score += 0.05

    score = max(0.0, min(1.0, score))
    keep = score >= 0.42
    return score, keep, "heuristic relevance/evidence estimate"




async def apply_final_source_cleanup(state: ResearchState) -> None:
    cfg = state.config
    if not bool(cfg.final_source_cleanup_enabled):
        state.log("Final source cleanup disabled")
        return
    if not state.extracted_sources:
        return

    state.log(f"Final source cleanup: start with {len(state.extracted_sources)} sources")
    deduped: list[ExtractedSource] = []
    seen: set[tuple[str, str]] = set()
    for source in state.extracted_sources:
        key = (source.url.rstrip("/").lower(), source.content_hash or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    if len(deduped) < len(state.extracted_sources):
        state.log(f"  Final exact dedup: removed {len(state.extracted_sources) - len(deduped)}")

    for source in deduped:
        h_score, h_keep, h_reason = _heuristic_final_quality(source)
        source._final_quality_score = h_score  # type: ignore[attr-defined]
        source._final_quality_keep = h_keep  # type: ignore[attr-defined]
        source._final_quality_reason = h_reason  # type: ignore[attr-defined]
        relevance = max(0.0, min(1.0, float(getattr(source, "relevance_score", 0.0) or 0.0)))
        source._final_score = (h_score * 0.7) + (relevance * 0.3)  # type: ignore[attr-defined]
    ranked = deduped
    ranked.sort(
        key=lambda source: (
            1 if bool(getattr(source, "_final_quality_keep", False)) else 0,
            float(getattr(source, "_final_score", 0.0) or 0.0),
            float(getattr(source, "_final_quality_score", 0.0) or 0.0),
            float(getattr(source, "relevance_score", 0.0) or 0.0),
            int(getattr(source, "char_count", 0) or 0),
        ),
        reverse=True,
    )

    keep_cap = max(1, int(cfg.synthesis_source_cap))
    min_quality = max(0.0, float(cfg.synthesis_min_source_quality))
    preferred = [source for source in ranked if bool(getattr(source, "_final_quality_keep", False))]
    if len(preferred) >= keep_cap:
        final_sources = preferred[:keep_cap]
    else:
        rejected = [
            source for source in ranked
            if not bool(getattr(source, "_final_quality_keep", False))
            and float(getattr(source, "_final_quality_score", 0.0) or 0.0) >= min_quality
        ]
        final_sources = preferred + rejected[: max(0, keep_cap - len(preferred))]

    state.log(
        f"  Final cleanup result: keep {len(final_sources)}/{len(ranked)} "
        f"(cap={keep_cap}, preferred={len(preferred)})"
    )
    state.extracted_sources = final_sources


def _source_synthesis_content(source: ExtractedSource) -> str:
    return _sanitize_content(source.summary or source.relevant_chunks or source.text or "")


def _content_type_priority(content_type: str, priority_list: list[str]) -> int:
    ct = (content_type or "other").lower().strip()
    try:
        return priority_list.index(ct)
    except ValueError:
        return len(priority_list)


def _build_source_block(
    source: ExtractedSource,
    index: int,
    per_source_budget: int,
) -> dict[str, Any] | None:
    content = _source_synthesis_content(source)
    if not content.strip():
        return None
    header = (
        f"\n[SOURCE {index}]\n"
        f"Title: {source.title}\n"
        f"URL: {source.url}\n"
    )
    if getattr(source, "sub_topic", ""):
        header += f"Sub-topic: {source.sub_topic}\n"
    if getattr(source, "content_type", ""):
        header += f"Type: {source.content_type}\n"
    header += "Content:\n"
    max_content_chars = max(500, per_source_budget - len(header) - 10)
    if len(content) > max_content_chars:
        content = content[:max_content_chars].rstrip()
    block = f"{header}{content}\n"
    return {
        "index": index,
        "title": source.title,
        "url": source.url,
        "block": block,
        "relevance_score": float(getattr(source, "relevance_score", 0.0) or 0.0),
        "final_score": float(getattr(source, "_final_score", 0.0) or 0.0),
        "sub_topic": getattr(source, "sub_topic", ""),
        "content_type": getattr(source, "content_type", ""),
    }


def _build_merge_grounding_context(
    state: ResearchState,
    all_blocks: list[dict[str, Any]],
) -> tuple[str, int, int]:
    """Return a compact top-source evidence pack for hierarchical merge prompts."""
    if not all_blocks:
        return "", 0, 0

    cfg = state.config
    fraction = max(0.0, min(1.0, float(getattr(cfg, "synthesis_merge_grounding_source_fraction", 0.30))))
    if fraction <= 0.0:
        return "", 0, 0

    target_count = max(1, ceil(len(all_blocks) * fraction))
    char_ratio = max(0.05, min(0.60, float(getattr(cfg, "synthesis_merge_grounding_char_ratio", 0.30))))
    char_budget = max(4000, int(float(cfg.synthesis_prompt_char_budget) * char_ratio))
    header = (
        "\nHigh-relevance source grounding context:\n"
        "These are the strongest original sources by final/relevance score. Use them to ground, verify, and recover details while merging the batch reports.\n"
    )
    used = len(header)
    parts: list[str] = []

    ranked = sorted(
        all_blocks,
        key=lambda block: (
            float(block.get("final_score", 0.0) or 0.0),
            float(block.get("relevance_score", 0.0) or 0.0),
            -int(block.get("index", 0) or 0),
        ),
        reverse=True,
    )
    for block in ranked[:target_count]:
        text = _sanitize_content(str(block.get("block", "") or ""))
        if not text:
            continue
        remaining = char_budget - used
        if remaining < 500:
            break
        if len(text) > remaining:
            text = text[:remaining].rstrip() + "\n"
        parts.append(text)
        used += len(text)

    if not parts:
        return "", 0, target_count
    return header + "".join(parts), len(parts), target_count


def _char_budget_batches(blocks: list[dict[str, Any]], budget: int) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current_batch: list[dict[str, Any]] = []
    current_chars = 0
    for block in blocks:
        block_len = len(block["block"])
        if current_batch and current_chars + block_len > budget:
            batches.append(current_batch)
            current_batch = []
            current_chars = 0
        current_batch.append(block)
        current_chars += block_len
    if current_batch:
        batches.append(current_batch)
    return batches


def _build_synthesis_source_batches(
    state: ResearchState,
    *,
    batch_char_budget: int,
) -> list[list[dict[str, Any]]]:
    batch_budget = max(12000, int(batch_char_budget))
    # Per-source char limit: from content profile override or global constant
    per_source_budget = int(
        getattr(state.config, "synthesis_char_budget_per_source", None)
        or SYNTH_CHAR_BUDGET_PER_SOURCE
    )
    priority_list = [
        "documentation", "research", "benchmark", "tutorial",
        "news", "opinion", "forum", "other",
    ]

    all_blocks: list[dict[str, Any]] = []
    skipped_empty = 0
    for index, source in enumerate(state.extracted_sources, 1):
        block = _build_source_block(source, index, per_source_budget)
        if block:
            all_blocks.append(block)
        else:
            skipped_empty += 1

    state.log(
        f"  Synthesis-ready sources: {len(all_blocks)}/{len(state.extracted_sources)} "
        f"(empty={skipped_empty})"
    )

    has_triage = any(block.get("sub_topic") for block in all_blocks)
    if not has_triage:
        state.log("  Synthesis batching: char-budget fallback (no triage grouping)")
        return _char_budget_batches(all_blocks, batch_budget)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for block in all_blocks:
        topic = (block.get("sub_topic") or "other").lower().strip()
        groups[topic].append(block)

    merged: dict[str, list[dict[str, Any]]] = {}
    other_group = list(groups.pop("other", []))
    for topic, items in groups.items():
        if len(items) < 2:
            other_group.extend(items)
        else:
            merged[topic] = items
    if other_group:
        merged["other"] = other_group

    for topic in merged:
        merged[topic].sort(
            key=lambda block: _content_type_priority(block.get("content_type", "other"), priority_list)
        )

    group_batches: dict[str, list[list[dict[str, Any]]]] = {}
    for topic, items in merged.items():
        group_batches[topic] = _char_budget_batches(items, batch_budget)

    batches: list[list[dict[str, Any]]] = []
    topic_keys = sorted(group_batches.keys())
    max_depth = max((len(items) for items in group_batches.values()), default=0)
    for depth in range(max_depth):
        for topic in topic_keys:
            if depth < len(group_batches[topic]):
                batches.append(group_batches[topic][depth])

    state.log(
        f"  Synthesis batching: smart groups={len(merged)} batches={len(batches)} "
        f"batch_budget={batch_budget} per_source={per_source_budget}"
    )
    return batches


def _format_source_range(items: list[dict[str, Any]]) -> str:
    indices = [int(item["index"]) for item in items]
    if not indices:
        return "none"
    if len(indices) == 1:
        return str(indices[0])
    return f"{indices[0]}-{indices[-1]}"


def _fallback_batch_report(
    state: ResearchState,
    batch: list[dict[str, Any]],
    batch_index: int,
    total_batches: int,
) -> str:
    findings = []
    for item in batch[:12]:
        source = state.extracted_sources[int(item["index"]) - 1]
        findings.append(
            f"- [{item['index']}] **{item['title']}**: {_source_evidence_brief(source, max_chars=420)}"
        )
    return (
        f"# Batch Report {batch_index}/{total_batches}\n\n"
        f"## Scope\nSources: {_format_source_range(batch)}\n\n"
        "## Key Findings\n"
        + ("\n".join(findings) if findings else "- No findings extracted.")
        + "\n\n## Notes\nGenerated from deterministic fallback because batch synthesis failed.\n"
    )


async def _synthesize_batch_report(
    state: ResearchState,
    batch: list[dict[str, Any]],
    *,
    batch_index: int,
    total_batches: int,
) -> str:
    cfg = state.config
    model = cfg.synthesis_model or cfg.query_model
    prompt = f"""You are an expert research analyst preparing one partial report for a larger hierarchical deep-research run.

Research question: "{state.question}"
Batch: {batch_index}/{total_batches}
Source coverage: {_format_source_range(batch)}

Use ONLY the sources below. Each source is labeled as [SOURCE N].
When citing facts, preserve the original source ids as [N].
Do not write a final polished conclusion for the whole research topic. Focus on dense extraction and organization of this batch's evidence.

Sources:
{"".join(item["block"] for item in batch)}

=== REQUIRED OUTPUT ===

# Batch Report {batch_index}/{total_batches}

## Batch Scope
Briefly explain what this batch covers.

## Detailed Findings
Capture all concrete facts, dates, numbers, benchmarks, product names, policy details, and technical claims from this batch.

## Contradictions and Open Questions
List uncertainties, disagreements, and missing pieces visible inside this batch.

## Fact Inventory
Use a flat bullet list of compact fact statements with citations.

=== RULES ===
1. Preserve source citations as [N].
2. Prefer high information density over elegance.
3. Use the same language as the research question.
4. Do not invent cross-batch facts.
5. Keep as much useful detail as possible from this batch.

=== BEGIN BATCH REPORT ==="""
    report = await call_llm(
        prompt=prompt,
        model=model,
        temperature=0.2,
        max_tokens=SYNTH_MAX_TOKENS_SINGLE,
        timeout=cfg.synthesis_timeout,
        debug_label=f"synth-batch-{batch_index}",
        debug_log=state.log,
    )
    if report:
        return report
    state.error(f"Synthesis batch {batch_index}/{total_batches} failed, using fallback")
    return _fallback_batch_report(state, batch, batch_index, total_batches)


def _build_merge_groups(
    reports: list[dict[str, Any]],
    *,
    prompt_char_budget: int,
) -> list[list[dict[str, Any]]]:
    budget = max(20000, int(prompt_char_budget))
    groups: list[list[dict[str, Any]]] = []
    current_group: list[dict[str, Any]] = []
    current_chars = 0
    for report in reports:
        text = _sanitize_content(report["text"] or "")
        if not text:
            continue
        header = (
            f"\n[BATCH REPORT {report['batch_index']}]\n"
            f"Coverage: {report['coverage']}\n"
            "Report:\n"
        )
        max_report_chars = max(3000, budget - len(header) - 10)
        if len(text) > max_report_chars:
            text = text[:max_report_chars].rstrip()
        block = f"{header}{text}\n"
        wrapped = dict(report)
        wrapped["block"] = block
        if current_group and current_chars + len(block) > budget:
            groups.append(current_group)
            current_group = []
            current_chars = 0
        current_group.append(wrapped)
        current_chars += len(block)
    if current_group:
        groups.append(current_group)
    return groups


def _fallback_merged_report(
    reports: list[dict[str, Any]],
    *,
    level: int,
    group_index: int,
) -> str:
    excerpts = []
    for report in reports:
        text = _compact_text(report["text"] or "")[:1200]
        excerpts.append(f"### Batch {report['batch_index']} ({report['coverage']})\n{text}")
    return (
        f"# Merged Report Level {level} Group {group_index}\n\n"
        "## Combined Batch Notes\n\n"
        + "\n\n".join(excerpts)
    )


async def _merge_batch_reports_hierarchically(
    state: ResearchState,
    leaf_reports: list[dict[str, Any]],
    *,
    grounding_context: str = "",
) -> str:
    cfg = state.config
    model = cfg.synthesis_model or cfg.query_model
    prompt_char_budget = max(20000, int(cfg.synthesis_prompt_char_budget))
    current_reports = list(leaf_reports)
    level = 1

    while len(current_reports) > 1:
        report_budget = max(20000, prompt_char_budget - len(grounding_context))
        groups = _build_merge_groups(current_reports, prompt_char_budget=report_budget)
        state.log(
            f"  Synthesis merge level {level}: {len(current_reports)} reports -> {len(groups)} groups"
        )
        next_reports: list[dict[str, Any]] = []
        for group_index, group in enumerate(groups, 1):
            grounding_section = f"\n{grounding_context}\n" if grounding_context else ""
            prompt = f"""You are an expert research analyst merging multiple partial reports into a unified research report.

Research question: "{state.question}"
Merge level: {level}
Group: {group_index}/{len(groups)}

The batch reports below already contain citations like [N] that refer to original sources.
The high-relevance source grounding context, if present, contains original source excerpts with the same [SOURCE N] ids.
Preserve and reuse those source citations.
Deduplicate repeated facts across batches, reconcile contradictions, and keep the report detailed.
{grounding_section}

Batch reports:
{"".join(item["block"] for item in group)}

=== REQUIRED OUTPUT ===

# [Descriptive Title]

## Executive Summary
2-4 paragraphs with concrete facts.

## Main Findings
Organize the strongest themes and evidence.

## Technical and Factual Details
Keep important numbers, dates, and comparisons.

## Contradictions and Information Gaps

## Conclusions

=== RULES ===
1. Preserve original citations [N].
2. Use ONLY information present in the batch reports or the high-relevance source grounding context.
3. Deduplicate aggressively, but do not collapse useful detail.
4. Use the same language as the research question.

=== BEGIN MERGED REPORT ==="""
            merged = await call_llm(
                prompt=prompt,
                model=model,
                temperature=0.2,
                max_tokens=SYNTH_MAX_TOKENS_MERGE,
                timeout=cfg.synthesis_timeout,
                debug_label=f"synth-merge-level-{level}-group-{group_index}",
                debug_log=state.log,
            )
            if not merged:
                state.error(
                    f"Synthesis merge level {level} group {group_index} failed, using fallback"
                )
                merged = _fallback_merged_report(group, level=level, group_index=group_index)
            next_reports.append(
                {
                    "batch_index": group_index,
                    "coverage": f"{group[0]['coverage']} -> {group[-1]['coverage']}",
                    "text": merged,
                }
            )
        current_reports = next_reports
        level += 1
    return current_reports[0]["text"] if current_reports else ""


# ---------------------------------------------------------------------------
# Single-shot synthesis (used when all sources fit in one context window)
# ---------------------------------------------------------------------------

_PROMPT_OVERHEAD_TOKENS: int = 900  # rough token budget for the prompt scaffolding itself


def _fits_in_single_context(all_blocks: list[dict[str, Any]]) -> bool:
    """Return True if every source block + prompt overhead fits within the model
    context window with at least CONTEXT_HEADROOM_RATIO headroom remaining."""
    available = int(MODEL_CONTEXT_TOKENS * (1.0 - CONTEXT_HEADROOM_RATIO))
    total = _PROMPT_OVERHEAD_TOKENS
    for block in all_blocks:
        total += count_tokens(block["block"])
        if total > available:
            return False
    return True


async def _synthesize_single_shot(
    state: ResearchState,
    all_blocks: list[dict[str, Any]],
) -> str:
    """Generate the final report in one LLM call when all sources fit in context."""
    cfg = state.config
    model = cfg.synthesis_model or cfg.query_model
    sources_text = "".join(item["block"] for item in all_blocks)
    prompt = f"""You are an expert research analyst writing a comprehensive research report.

Research question: "{state.question}"
Total sources: {len(all_blocks)}

All sources are provided below. Each source is labeled [SOURCE N].
When citing facts, use [N] to reference the original source.

{sources_text}

=== REQUIRED OUTPUT ===

# [Descriptive Title]

## Executive Summary
3-5 paragraphs covering the main findings with concrete facts and citations.

## Main Findings
Organize the strongest themes and evidence from all sources.

## Technical and Factual Details
Keep all important numbers, dates, benchmarks, and comparisons.

## Contradictions and Information Gaps
Note where sources disagree or where information is missing.

## Conclusions
Summarize the most important takeaways.

=== RULES ===
1. Preserve source citations as [N].
2. Prefer high information density over elegance.
3. Use the same language as the research question.
4. Do not invent facts not present in the sources.
5. Keep as much useful detail as possible.

=== BEGIN REPORT ==="""

    state.log(f"  Single-shot synthesis: {len(all_blocks)} sources in one context window")
    report = await call_llm(
        prompt=prompt,
        model=model,
        temperature=0.2,
        max_tokens=SYNTH_MAX_TOKENS_MERGE,
        timeout=cfg.synthesis_timeout,
        debug_label="synth-single-shot",
        debug_log=state.log,
    )
    if report:
        return report
    state.error("Single-shot synthesis failed, falling back to batch mode")
    return ""


async def run_synthesize(state: ResearchState) -> PhaseResult:
    """Phase 5: bounded cleanup + hierarchical synthesis."""
    t0 = time.time()
    cfg = state.config
    state.synthesis_batch_reports = []
    if not state.extracted_sources:
        state.final_report = (
            f"# Research: {state.question}\n\n"
            "No relevant sources were found."
        )
        if "synthesize" not in state.completed_phases:
            state.completed_phases.append("synthesize")
        return PhaseResult(phase_name="synthesize", success=True, items_produced=0, duration_sec=0.0)

    await apply_final_source_cleanup(state)
    if not state.extracted_sources:
        state.final_report = (
            f"# Research: {state.question}\n\n"
            "No synthesis-ready source content was available after filtering."
        )
        if "synthesize" not in state.completed_phases:
            state.completed_phases.append("synthesize")
        return PhaseResult(phase_name="synthesize", success=True, items_produced=0, duration_sec=0.0)

    # Run triage once on the final curated pool so that sub_topic / content_type /
    # evidence_strength are available for smart synthesis batching.
    if getattr(state.config, "triage_before_synth", False) and state.extracted_sources:
        from services.deep_research.triage import run_triage
        await run_triage(state)

    state.log(f"Synthesizing from {len(state.extracted_sources)} sources...")
    source_batches = _build_synthesis_source_batches(
        state,
        batch_char_budget=int(cfg.synthesis_batch_char_budget),
    )
    if not source_batches:
        state.final_report = (
            f"# Research: {state.question}\n\n"
            "No synthesis-ready source content was available after filtering."
        )
    else:
        # Flatten all blocks to check whether everything fits in one context window.
        all_blocks = [block for batch in source_batches for block in batch]

        if _fits_in_single_context(all_blocks):
            # All sources fit — skip batching entirely, generate the report in one pass.
            state.log(
                f"  Single-context synthesis: all {len(all_blocks)} sources fit within "
                f"{MODEL_CONTEXT_TOKENS} tokens (skipping batch/merge pipeline)"
            )
            report = await _synthesize_single_shot(state, all_blocks)
            if report:
                state.final_report = report
            else:
                # Single-shot failed — fall through to batch flow below
                state.log("  Single-shot failed, falling back to hierarchical batch synthesis")
                source_batches = source_batches  # already built, reuse

        if not state.final_report:
            grounding_context, grounding_included, grounding_target = _build_merge_grounding_context(
                state,
                all_blocks,
            )
            if grounding_context:
                state.log(
                    "  Hierarchical merge grounding: "
                    f"{grounding_included}/{len(all_blocks)} top sources "
                    f"(target={grounding_target}, chars={len(grounding_context)})"
                )
            state.log(
                f"  Hierarchical synthesis: {len(source_batches)} source batches "
                f"(target {int(cfg.synthesis_batch_char_budget)} chars each)"
            )
            leaf_reports: list[dict[str, Any]] = []
            for batch_index, batch in enumerate(source_batches, 1):
                state.log(
                    f"  Synthesis batch {batch_index}/{len(source_batches)}: "
                    f"{len(batch)} sources ({_format_source_range(batch)})"
                )
                report = await _synthesize_batch_report(
                    state,
                    batch,
                    batch_index=batch_index,
                    total_batches=len(source_batches),
                )
                state.synthesis_batch_reports.append(report)
                leaf_reports.append(
                    {
                        "batch_index": batch_index,
                        "coverage": _format_source_range(batch),
                        "text": report,
                    }
                )

            if len(leaf_reports) == 1:
                state.final_report = leaf_reports[0]["text"]
            else:
                report = await _merge_batch_reports_hierarchically(
                    state,
                    leaf_reports,
                    grounding_context=grounding_context,
                )
                if report:
                    state.final_report = report
                else:
                    state.error("Hierarchical synthesis failed, using concatenated batch fallback")
                    state.final_report = "\n\n".join(
                        f"## Batch {i}\n\n{r}"
                        for i, r in enumerate(state.synthesis_batch_reports, 1)
                    )

        # Last-resort: if every synthesis path failed, dump raw source content
        if not state.final_report or not state.final_report.strip():
            state.error("All synthesis paths failed, dumping raw source content")
            lines = [f"# Research: {state.question}\n\n*Synthesis failed — raw source content below.*\n"]
            for i, src in enumerate(state.extracted_sources, 1):
                content = _sanitize_content(
                    src.summary or src.relevant_chunks or src.text or ""
                )[:2000]
                if content:
                    lines.append(f"\n## [{i}] {src.title}\n\n{content}\n")
            state.final_report = "\n".join(lines)

        # Append sources footer (numbered reference list with URLs)
        if state.extracted_sources:
            footer_lines = ["\n\n---\n\n## Sources\n"]
            for i, src in enumerate(state.extracted_sources, 1):
                footer_lines.append(f"{i}. [{src.title}]({src.url})")
            state.final_report += "\n".join(footer_lines) + "\n"

    dt = time.time() - t0
    state.log(f"Synthesis complete: {len(state.final_report)} chars in {dt:.1f}s")
    if "synthesize" not in state.completed_phases:
        state.completed_phases.append("synthesize")
    return PhaseResult(phase_name="synthesize", success=True, items_produced=1, duration_sec=dt)


__all__ = [
    "apply_final_source_cleanup",
    "run_synthesize",
    "_build_synthesis_source_batches",
]
