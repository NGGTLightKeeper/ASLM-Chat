# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Agentic deep research read_page tool."""

from __future__ import annotations

import re

from core.extract.scoring import densify_text_gliner
from services.deep_research.models import ResearchSession
from services.deep_research.tools.base import summarize_text
from services.read_page import run_read_page


def _dense_observation(text: str, limit: int) -> str:
    """Entity-dense observation: GliNER paragraph ranking with truncation fallback."""
    try:
        result = densify_text_gliner(text, output_chars=limit)
        if result and len(result.strip()) > 50:
            return result
    except Exception:
        pass
    return summarize_text(text, limit)


def chunk_text(text: str, chunk_chars: int, overlap: int) -> list[str]:
    if not text:
        return []
    size = max(1000, int(chunk_chars))
    ov = max(0, min(int(overlap), size // 3))
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - ov, start + 1)
    return [chunk for chunk in chunks if chunk]


def window_around_query(text: str, query: str, limit: int) -> str:
    if not query.strip():
        return text[:limit]
    terms = [re.escape(term) for term in query.split() if len(term) > 2]
    if not terms:
        return text[:limit]
    match = re.search("|".join(terms), text, flags=re.IGNORECASE)
    if not match:
        return text[:limit]
    half = max(500, limit // 2)
    start = max(0, match.start() - half)
    end = min(len(text), match.end() + half)
    return text[start:end].strip()


async def run_agent_read_page(
    session: ResearchSession,
    *,
    source: str,
    mode: str = "full",
    query: str = "",
) -> str:
    cfg = session.config
    source_card = session.source_by_id_or_url(source)
    if source_card is None:
        return f"Cannot read page: source not found: {source}"

    raw = await run_read_page(
        source_card.url,
        timeout=float(cfg.read_timeout_sec),
        use_wayback_fallback=bool(getattr(cfg, "read_wayback_fallback", True)),
        max_chars=int(cfg.read_page_max_chars),
    )
    session.read_calls += 1
    normalized_mode = (mode or "full").strip().lower()
    truncated = "[...truncated]" in raw

    if normalized_mode == "chunks":
        chunks = chunk_text(raw, int(cfg.read_chunk_chars), int(cfg.read_chunk_overlap))
        content = "\n\n".join(
            f"[chunk {index + 1}/{len(chunks)}]\n{chunk}"
            for index, chunk in enumerate(chunks[:4])
        )
    elif normalized_mode in {"window", "find"}:
        content = window_around_query(raw, query, min(8_000, int(cfg.read_page_max_chars)))
        chunks = [content]
    elif normalized_mode == "summary_stub":
        content = summarize_text(raw, min(2_000, int(cfg.read_page_max_chars)))
        chunks = [content]
    else:
        content = raw[: int(cfg.read_page_max_chars)]
        chunks = chunk_text(content, int(cfg.read_chunk_chars), int(cfg.read_chunk_overlap))

    artifact = session.add_read_artifact(
        source_card,
        mode=normalized_mode,
        content=content,
        chunks=chunks,
        query=query,
        truncated=truncated,
    )
    obs_limit = int(cfg.tool_observation_max_chars)
    if normalized_mode in {"full", "chunks"}:
        observation = _dense_observation(content, obs_limit)
    else:
        observation = summarize_text(content, obs_limit)

    return (
        f"Read {artifact.id} from {source_card.id}: {source_card.title}\n"
        f"mode={normalized_mode} chars={len(content)} chunks={len(chunks)}\n"
        f"{observation}"
    )
