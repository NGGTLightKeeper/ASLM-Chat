# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Final synthesis for agentic deep research."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from core.llm.llm_client import call_llm, call_llm_json
from services.deep_research.models import ResearchSession, SourceCard
from services.deep_research.prompts import build_cluster_prompt, build_compression_prompt, build_synthesis_prompt, synthesis_schema


def _fallback_markdown(session: ResearchSession, reason: str = "") -> str:
    title = f"# Research: {session.question}"
    lines = [title, ""]
    if reason:
        lines.append(f"*Fallback synthesis: {reason}*")
        lines.append("")
    if session.final_brief and session.final_brief.summary:
        lines.extend(["## Summary", session.final_brief.summary, ""])
    if session.claims:
        lines.append("## Working Claims")
        lines.extend(f"- {claim}" for claim in session.claims)
        lines.append("")
    if session.gaps:
        lines.append("## Gaps")
        lines.extend(f"- {gap}" for gap in session.gaps)
        lines.append("")
    if session.read_artifacts:
        lines.append("## Evidence Notes")
        for artifact in session.read_artifacts[:8]:
            excerpt = artifact.content[:1200].strip()
            lines.append(f"### {artifact.id} from {artifact.source_id}")
            lines.append(excerpt)
            lines.append("")
    if session.console_outputs:
        lines.append("## Console Outputs")
        for output in session.console_outputs[-5:]:
            lines.append("```text")
            lines.append(output[:1500])
            lines.append("```")
        lines.append("")
    lines.append("## Sources")
    if session.source_pool:
        for source in session.source_pool:
            lines.append(f"- [{source.id}] [{source.title}]({source.url})")
    else:
        lines.append("- No sources collected.")
    return "\n".join(lines).strip() + "\n"


def _render_json_report(payload: object, session: ResearchSession) -> str:
    if not isinstance(payload, dict):
        return _fallback_markdown(session, "synthesis returned no JSON")
    title = str(payload.get("title") or f"Research: {session.question}").strip()
    summary = str(payload.get("summary") or "").strip()
    lines = [f"# {title}", ""]
    if summary:
        lines.extend(["## Summary", summary, ""])
    sections = payload.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            heading = str(section.get("heading") or "Findings").strip()
            body = str(section.get("body") or "").strip()
            if body:
                lines.extend([f"## {heading}", body, ""])
    lines.append("## Sources")
    source_items = payload.get("sources")
    rendered = set()
    if isinstance(source_items, list):
        for item in source_items:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("id") or "").strip()
            title_text = str(item.get("title") or sid or "Source").strip()
            url = str(item.get("url") or "").strip()
            if sid:
                rendered.add(sid)
            lines.append(f"- [{sid}] [{title_text}]({url})" if url else f"- [{sid}] {title_text}")
    for source in session.source_pool:
        if source.id not in rendered:
            lines.append(f"- [{source.id}] [{source.title}]({source.url})")
    return "\n".join(lines).strip() + "\n"


def _cluster_sources(sources: list[SourceCard]) -> dict[str, list[SourceCard]]:
    clusters: dict[str, list[SourceCard]] = defaultdict(list)
    for source in sources:
        key = source.trust_tier or "unknown"
        clusters[key].append(source)
    return dict(clusters)


async def _summarize_cluster(session: ResearchSession, name: str, sources: list[SourceCard]) -> str:
    source_text = "\n".join(
        f"{source.id}. {source.title}\nURL: {source.url}\nSnippet: {source.snippet[:800]}"
        for source in sources
    )
    prompt = build_cluster_prompt(session.question, name, source_text)
    result = await call_llm_json(
        prompt=prompt,
        model=session.config.synthesis_model or session.config.query_model,
        temperature=0.2,
        structured_output=False,
        timeout=min(120.0, float(session.config.controller_timeout_sec)),
    )
    if isinstance(result, str):
        return result
    return f"### Cluster {name}\n{source_text[:4000]}"


def _artifact_total_chars(session: ResearchSession) -> int:
    return sum(a.char_count or len(a.content) for a in session.read_artifacts)


def _batch_artifacts(session: ResearchSession, batch_chars: int) -> list[str]:
    """Split read artifacts into text batches of ≤ batch_chars each."""
    batches: list[str] = []
    current_parts: list[str] = []
    current_len = 0
    for artifact in session.read_artifacts:
        header = f"[{artifact.id} from {artifact.source_id} | {artifact.url}]\n"
        body = artifact.content[:batch_chars]
        block = header + body + "\n"
        if current_len + len(block) > batch_chars and current_parts:
            batches.append("".join(current_parts))
            current_parts = []
            current_len = 0
        current_parts.append(block)
        current_len += len(block)
    if current_parts:
        batches.append("".join(current_parts))
    return batches


async def _compress_batch(session: ResearchSession, batch_text: str) -> str:
    prompt = build_compression_prompt(session.question, batch_text)
    cfg = session.config
    try:
        result = await call_llm(
            prompt=prompt,
            model=cfg.synthesis_model or cfg.query_model,
            temperature=0.15,
            structured_output=False,
            timeout=min(120.0, float(cfg.controller_timeout_sec) * 1.5),
        )
        return str(result or "").strip()
    except Exception:
        return batch_text[:int(cfg.artifact_compression_output_chars)]


async def _compress_artifacts(session: ResearchSession) -> str:
    """Run parallel LLM compression over all read artifacts and return combined essay."""
    cfg = session.config
    batches = _batch_artifacts(session, int(cfg.artifact_compression_batch_chars))
    if not batches:
        return ""
    tasks = [_compress_batch(session, batch) for batch in batches]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    parts = [str(r) for r in results if not isinstance(r, Exception) and r]
    return "\n\n---\n\n".join(parts)


async def synthesize_report(session: ResearchSession) -> str:
    """Produce the final Markdown report."""
    cfg = session.config

    # Pre-synthesis compression: extract primary claims from artifacts before synthesis.
    # Triggered when total artifact content exceeds the threshold.
    compressed_artifacts: str | None = None
    total_artifact_chars = _artifact_total_chars(session)
    if total_artifact_chars > int(cfg.artifact_compression_threshold_chars):
        compressed_artifacts = await _compress_artifacts(session)

    clustered_reports: list[str] = []
    if session.synthesis_context_estimate() > int(session.config.synthesis_context_budget):
        clusters = _cluster_sources(session.source_pool)
        tasks = [
            _summarize_cluster(session, name, sources)
            for name, sources in list(clusters.items())[:6]
        ]
        cluster_results = await asyncio.gather(*tasks, return_exceptions=True)
        clustered_reports = [
            str(item) for item in cluster_results if not isinstance(item, Exception)
        ]

    prompt = build_synthesis_prompt(
        session,
        clustered_reports=clustered_reports,
        compressed_artifacts=compressed_artifacts,
    )
    try:
        payload = await call_llm_json(
            prompt=prompt,
            model=session.config.synthesis_model or session.config.query_model,
            temperature=float(session.config.synthesis_temperature),
            json_schema=synthesis_schema(),
            schema_name="deep_research_synthesis",
            structured_output=bool(session.config.structured_output_enabled),
            strict=bool(session.config.structured_output_strict),
            timeout=min(240.0, max(60.0, float(session.config.controller_timeout_sec) * 2)),
        )
    except Exception as exc:
        markdown = await _synthesize_markdown_fallback(session, clustered_reports, compressed_artifacts)
        return markdown or _fallback_markdown(session, f"LLM synthesis failed: {type(exc).__name__}: {exc}")
    if payload is None:
        markdown = await _synthesize_markdown_fallback(session, clustered_reports, compressed_artifacts)
        return markdown or _fallback_markdown(session, "LLM synthesis failed")
    return _render_json_report(payload, session)


async def _synthesize_markdown_fallback(
    session: ResearchSession,
    clustered_reports: list[str],
    compressed_artifacts: str | None = None,
) -> str:
    prompt = build_synthesis_prompt(
        session,
        clustered_reports=clustered_reports,
        compressed_artifacts=compressed_artifacts,
    ).replace(
        "Return JSON with title, summary, sections, sources.",
        (
            "Return Markdown only. Produce a useful technical report, not a thin summary. "
            "Cite sources with ids like [S001], include practical steps/examples where supported, "
            "and include a Sources section."
        ),
    )
    try:
        result = await call_llm(
            prompt=prompt,
            model=session.config.synthesis_model or session.config.query_model,
            temperature=min(0.2, float(session.config.synthesis_temperature)),
            structured_output=False,
            timeout=min(120.0, max(45.0, float(session.config.controller_timeout_sec))),
        )
    except Exception:
        return ""
    text = str(result or "").strip()
    if not text:
        return ""
    if not text.startswith("#"):
        text = f"# Research: {session.question}\n\n{text}"
    return text.rstrip() + "\n"
