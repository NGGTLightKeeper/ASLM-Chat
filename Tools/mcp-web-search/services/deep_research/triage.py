# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Phase 3 — Triage.

Annotates each extracted source with structured metadata via batched
LLM calls.  Port of legacy deep-research/src/triage.py.  Falls back
to heuristic annotation when LLM is unavailable.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlparse

from services.deep_research.config import TRIAGE_MAX_CONCURRENT_BATCHES
from services.deep_research.models import (
    ExtractedSource,
    PhaseResult,
    ResearchState,
)
from core.llm.llm_client import call_llm_json


# ---------------------------------------------------------------------------
# Annotation model
# ---------------------------------------------------------------------------

@dataclass
class TriageAnnotation:
    sub_topic: str = ""
    content_type: str = "other"
    evidence_strength: str = "moderate"
    source_character: str = "secondary"
    perspective: str = ""


VALID_CONTENT_TYPES = {
    "documentation", "research", "benchmark", "tutorial",
    "news", "opinion", "forum", "other",
}
VALID_EVIDENCE_STRENGTHS = {"strong", "moderate", "weak", "anecdotal"}
VALID_SOURCE_CHARACTERS = {"primary", "secondary", "aggregator", "commentary"}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _triage_schema(batch_size: int) -> dict:
    return {
        "type": "array",
        "minItems": batch_size,
        "maxItems": batch_size,
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "sub_topic", "content_type", "evidence_strength",
                "source_character", "perspective",
            ],
            "properties": {
                "sub_topic": {"type": "string", "minLength": 1, "maxLength": 160},
                "content_type": {"type": "string", "enum": sorted(VALID_CONTENT_TYPES)},
                "evidence_strength": {"type": "string", "enum": sorted(VALID_EVIDENCE_STRENGTHS)},
                "source_character": {"type": "string", "enum": sorted(VALID_SOURCE_CHARACTERS)},
                "perspective": {"type": "string", "minLength": 0, "maxLength": 160},
            },
        },
    }


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def _build_prompt(
    sources: List[ExtractedSource],
    question: str,
    query_type: str,
) -> str:
    blocks: List[str] = []
    for i, src in enumerate(sources):
        domain = urlparse(src.url).netloc
        text_preview = src.text[:800] if src.text else "(no text)"
        blocks.append(
            f"Source {i + 1}:\n"
            f"  URL: {src.url}\n"
            f"  Title: {src.title}\n"
            f"  Domain: {domain}\n"
            f"  Text preview: {text_preview}"
        )

    return (
        "You are a research source triage system. Analyze each source and assign structured metadata.\n\n"
        f"Research question: {question}\n"
        f"Query type: {query_type}\n\n"
        "Sources to triage:\n"
        + "\n\n".join(blocks)
        + "\n\n"
        "For each source, assign:\n"
        "- sub_topic: specific sub-topic this source addresses (short phrase)\n"
        "- content_type: one of [documentation, research, benchmark, tutorial, news, opinion, forum, other]\n"
        "- evidence_strength: one of [strong, moderate, weak, anecdotal]\n"
        "- source_character: one of [primary, secondary, aggregator, commentary]\n"
        "- perspective: brief description of the source's angle\n\n"
        "Respond with JSON only — an array of objects in source order."
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_response(data: object, batch_size: int) -> List[Optional[TriageAnnotation]]:
    if not isinstance(data, list):
        return [None] * batch_size

    results: List[Optional[TriageAnnotation]] = []
    for item in data[:batch_size]:
        if not isinstance(item, dict):
            results.append(None)
            continue
        ct = str(item.get("content_type", "other")).lower().strip()
        es = str(item.get("evidence_strength", "moderate")).lower().strip()
        sc = str(item.get("source_character", "secondary")).lower().strip()
        results.append(TriageAnnotation(
            sub_topic=str(item.get("sub_topic", "")).strip(),
            content_type=ct if ct in VALID_CONTENT_TYPES else "other",
            evidence_strength=es if es in VALID_EVIDENCE_STRENGTHS else "moderate",
            source_character=sc if sc in VALID_SOURCE_CHARACTERS else "secondary",
            perspective=str(item.get("perspective", "")).strip(),
        ))
    while len(results) < batch_size:
        results.append(None)
    return results


def _heuristic_annotation(
    question: str,
    source: Optional["ExtractedSource"] = None,
) -> TriageAnnotation:
    """Fallback annotation when LLM is unavailable.

    Uses the source title (if available) as sub_topic so that different sources
    end up in different clusters rather than all collapsing into "general".
    """
    sub_topic = question[:80]
    if source is not None:
        if source.title and len(source.title.strip()) > 4:
            sub_topic = source.title.strip()[:80]
        else:
            try:
                domain = urlparse(source.url).netloc.replace("www.", "")
                if domain:
                    sub_topic = domain
            except Exception:
                pass
    return TriageAnnotation(
        sub_topic=sub_topic,
        content_type="other",
        evidence_strength="moderate",
        source_character="secondary",
        perspective="",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_triage(
    state: ResearchState,
    sources: list[ExtractedSource] | None = None,
) -> PhaseResult:
    """Phase 3: annotate sources with triage metadata."""
    t0 = time.time()
    cfg = state.config
    sources = sources if sources is not None else state.extracted_sources

    if not sources:
        state.log("Triage: no sources to annotate")
        if "triage" not in state.completed_phases:
            state.completed_phases.append("triage")
        return PhaseResult(phase_name="triage", items_produced=0, duration_sec=0.0)

    batch_size = cfg.triage_batch_size
    model = cfg.triage_model or cfg.query_model
    state.log(f"Triage: annotating {len(sources)} sources (batch={batch_size})")

    batches = [sources[i:i + batch_size] for i in range(0, len(sources), batch_size)]
    sem = asyncio.Semaphore(TRIAGE_MAX_CONCURRENT_BATCHES)

    async def _process_batch(batch: List[ExtractedSource]) -> List[Optional[TriageAnnotation]]:
        async with sem:
            prompt = _build_prompt(batch, state.question, state.query_type)
            try:
                data = await call_llm_json(
                    prompt=prompt,
                    model=model,
                    temperature=0.1,
                    json_schema=_triage_schema(len(batch)),
                    schema_name="research_source_triage",
                    structured_output=cfg.structured_output_enabled,
                    strict=cfg.structured_output_strict,
                    # Triage is a classification task — reasoning tokens consume
                    # output budget without improving accuracy here.
                    reasoning_effort="",
                    reasoning_tokens=0,
                    concise_reasoning_prompt=cfg.concise_reasoning_prompt,
                    timeout=cfg.triage_timeout,
                    debug_label="triage",
                    debug_log=state.log,
                )
                return _parse_response(data, len(batch))
            except Exception as exc:
                state.log(f"  Triage batch failed: {type(exc).__name__}: {exc}")
                return [None] * len(batch)

    batch_results = await asyncio.gather(*[_process_batch(b) for b in batches])
    flat = [ann for batch_ann in batch_results for ann in batch_ann]

    annotated = 0
    for src, ann in zip(sources, flat):
        if ann is None:
            ann = _heuristic_annotation(state.question, src)
        else:
            annotated += 1
        src.sub_topic = ann.sub_topic
        src.content_type = ann.content_type
        src.evidence_strength = ann.evidence_strength
        src.source_character = ann.source_character
        src.perspective = ann.perspective

    state.log(f"Triage complete: {annotated}/{len(sources)} annotated by LLM")

    dt = time.time() - t0
    if "triage" not in state.completed_phases:
        state.completed_phases.append("triage")
    return PhaseResult(phase_name="triage", items_produced=annotated, duration_sec=dt)
