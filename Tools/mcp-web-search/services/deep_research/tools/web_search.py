# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Agentic deep research web search tool."""

from __future__ import annotations

from services.deep_research.models import ResearchSession, SourceCard
from services.deep_research.tools.base import summarize_text
from services.web_search import run_web_search_structured


async def run_agent_web_search(session: ResearchSession, query: str) -> str:
    cfg = session.config
    results = await run_web_search_structured(
        query=query,
        max_results=int(cfg.search_results_per_call),
        hard_timeout=float(cfg.search_timeout_sec),
    )
    session.search_calls += 1
    cards = [
        SourceCard(
            id="",
            url=item.url,
            title=item.title,
            snippet=item.snippet,
            trust_tier=getattr(item, "trust_tier", "?") or "?",
            score=float(getattr(item, "score", 0.0) or 0.0),
            engine=getattr(item, "engine", "") or "",
        )
        for item in results
    ]
    inserted = session.add_sources(cards)
    if not inserted:
        return f"No new sources found for query: {query}"

    lines = [f"Added {len(inserted)} sources for query: {query}"]
    for source in inserted[:8]:
        lines.append(
            f"{source.id}: {source.title} ({source.url}) "
            f"trust={source.trust_tier} score={source.score:.2f} "
            f"snippet={summarize_text(source.snippet, 240)}"
        )
    return "\n".join(lines)
