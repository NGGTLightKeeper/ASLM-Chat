# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""LLM-based triage with metadata annotation for extracted sources.

Each source is annotated with sub_topic, content_type, evidence_strength,
source_character, and perspective via batched LLM calls.  Falls back to
heuristic annotation when the LLM is unavailable or returns invalid JSON.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class TriageAnnotation:
    """Structured triage metadata for one source."""

    sub_topic: str = ""
    content_type: str = "other"
    evidence_strength: str = "moderate"
    source_character: str = "secondary"
    perspective: str = ""


# Valid values for validation.
VALID_CONTENT_TYPES = {
    "documentation", "research", "benchmark", "tutorial",
    "news", "opinion", "forum", "other",
}
VALID_EVIDENCE_STRENGTHS = {"strong", "moderate", "weak", "anecdotal"}
VALID_SOURCE_CHARACTERS = {"primary", "secondary", "aggregator", "commentary"}


def _triage_json_schema(batch_size: int) -> dict:
    """Return a strict JSON schema for one triage batch."""

    return {
        "type": "array",
        "minItems": batch_size,
        "maxItems": batch_size,
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "sub_topic",
                "content_type",
                "evidence_strength",
                "source_character",
                "perspective",
            ],
            "properties": {
                "sub_topic": {"type": "string", "minLength": 1, "maxLength": 160},
                "content_type": {"type": "string", "enum": sorted(VALID_CONTENT_TYPES)},
                "evidence_strength": {
                    "type": "string",
                    "enum": sorted(VALID_EVIDENCE_STRENGTHS),
                },
                "source_character": {
                    "type": "string",
                    "enum": sorted(VALID_SOURCE_CHARACTERS),
                },
                "perspective": {"type": "string", "minLength": 0, "maxLength": 160},
            },
        },
    }


def _heuristic_annotation(
    source,
    question: str,
    domain_topics: list[str],
) -> TriageAnnotation:
    """Build a best-effort annotation without LLM, using domain metadata."""
    content_type = "other"
    topic_to_type = {
        "tech": "documentation",
        "academic": "research",
        "news": "news",
        "general": "other",
        "shopping": "other",
        "finance": "news",
        "medical": "research",
    }
    for topic in domain_topics:
        if topic in topic_to_type:
            content_type = topic_to_type[topic]
            break

    return TriageAnnotation(
        sub_topic=question,
        content_type=content_type,
        evidence_strength="moderate",
        source_character="secondary",
        perspective="",
    )


def _build_triage_prompt(
    sources_batch: list,
    question: str,
    query_type: str,
    domain_hints: dict[str, list[str]],
) -> str:
    """Build the LLM prompt for triaging a batch of sources."""
    source_blocks = []
    for i, src in enumerate(sources_batch):
        domain = urlparse(src.url).netloc
        topics = domain_hints.get(domain, [])
        topic_hint = f" (domain topics: {', '.join(topics)})" if topics else ""
        text_preview = src.text[:800] if src.text else "(no text)"
        source_blocks.append(
            f"Source {i + 1}:\n"
            f"  URL: {src.url}\n"
            f"  Title: {src.title}\n"
            f"  Domain{topic_hint}\n"
            f"  Text preview: {text_preview}"
        )

    sources_text = "\n\n".join(source_blocks)

    return f"""You are a research source triage system. Analyze each source and assign structured metadata.

Research question: {question}
Query type: {query_type}

Sources to triage:
{sources_text}

For each source, assign:
- sub_topic: specific sub-topic this source addresses (short phrase)
- content_type: one of [documentation, research, benchmark, tutorial, news, opinion, forum, other]
- evidence_strength: one of [strong, moderate, weak, anecdotal]
- source_character: one of [primary, secondary, aggregator, commentary]
- perspective: brief description of the source's angle (e.g., "vendor perspective", "academic", "user experience")

Respond with JSON only — an array of objects in the same order as the sources:
[
  {{
    "sub_topic": "...",
    "content_type": "...",
    "evidence_strength": "...",
    "source_character": "...",
    "perspective": "..."
  }}
]"""


def _parse_triage_response(
    data: object,
    batch_size: int,
) -> list[Optional[TriageAnnotation]]:
    """Parse and validate a triage LLM response into annotations."""
    if not isinstance(data, list):
        return [None] * batch_size

    results: list[Optional[TriageAnnotation]] = []
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

    # Pad if LLM returned fewer items than expected.
    while len(results) < batch_size:
        results.append(None)
    return results


async def triage_sources(
    sources: list,
    question: str,
    query_type: str,
    domain_registry,
    config,
) -> list:
    """Annotate extracted sources with triage metadata via batched LLM calls.

    Sources are modified in-place and also returned for convenience.
    Falls back to heuristic annotation on LLM failure.
    """
    from .llm_client import call_llm_json

    batch_size = getattr(config, "triage_batch_size", 4)
    model = getattr(config, "triage_model", "")
    timeout = getattr(config, "triage_timeout", 60.0)

    # Pre-build domain topic hints for all sources.
    domain_hints: dict[str, list[str]] = {}
    for src in sources:
        domain = urlparse(src.url).netloc
        if domain not in domain_hints:
            try:
                info = domain_registry.lookup(src.url)
                domain_hints[domain] = info.topics if info else []
            except Exception:
                domain_hints[domain] = []

    # Split into batches and process concurrently.
    batches = [
        sources[i : i + batch_size]
        for i in range(0, len(sources), batch_size)
    ]

    async def _process_batch(batch: list) -> list[Optional[TriageAnnotation]]:
        prompt = _build_triage_prompt(batch, question, query_type, domain_hints)
        try:
            data = await call_llm_json(
                prompt=prompt,
                model=model,
                temperature=0.1,
                json_schema=_triage_json_schema(len(batch)),
                schema_name="research_source_triage",
                structured_output=bool(getattr(config, "structured_output_enabled", True)),
                strict=bool(getattr(config, "structured_output_strict", True)),
                reasoning_effort=str(getattr(config, "reasoning_effort", "low")),
                reasoning_tokens=int(getattr(config, "reasoning_tokens", 2048)),
                concise_reasoning_prompt=str(getattr(config, "concise_reasoning_prompt", "")),
                timeout=timeout,
            )
            return _parse_triage_response(data, len(batch))
        except Exception as exc:
            logger.warning("Triage LLM call failed: %s", exc)
            return [None] * len(batch)

    batch_results = await asyncio.gather(*[_process_batch(b) for b in batches])

    # Flatten and apply annotations.
    flat_annotations = [ann for batch_ann in batch_results for ann in batch_ann]

    for src, annotation in zip(sources, flat_annotations):
        if annotation is None:
            domain = urlparse(src.url).netloc
            annotation = _heuristic_annotation(
                src, question, domain_hints.get(domain, [])
            )
        src.sub_topic = annotation.sub_topic
        src.content_type = annotation.content_type
        src.evidence_strength = annotation.evidence_strength
        src.source_character = annotation.source_character
        src.perspective = annotation.perspective

    annotated = sum(1 for a in flat_annotations if a is not None)
    logger.info(
        "triage_sources: %d/%d sources annotated by LLM, %d heuristic fallback",
        annotated,
        len(sources),
        len(sources) - annotated,
    )
    return sources
