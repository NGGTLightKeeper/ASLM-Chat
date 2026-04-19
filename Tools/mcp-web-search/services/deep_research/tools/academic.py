# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Academic search tool for deep research."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from core.fetch.academic_fetcher import AcademicFetcher
from core.registry.trust_registry import TrustRegistry
from services.deep_research.models import SourceCard

try:
    _trust = TrustRegistry()
except Exception:
    _trust = None  # type: ignore[assignment]


def _tier_for_url(url: str) -> str:
    if _trust is not None:
        tier = _trust.get_tier(url)
        if tier:
            return tier
    return "moderate"

if TYPE_CHECKING:
    from services.deep_research.models import ResearchSession

logger = logging.getLogger("services.deep_research.tools.academic")

async def run_agent_academic_search(
    session: ResearchSession,
    query: str,
    target_domains: Optional[list[str]] = None,
) -> str:
    """Execute academic search and update source pool."""
    
    fetcher = AcademicFetcher(timeout=float(session.config.search_timeout_sec))
    results = await fetcher.search(query, target_domains=target_domains)

    if not results:
        return f"No academic results found for: {query}"

    cards = [
        SourceCard(
            id="",
            url=res.url,
            title=res.title,
            snippet=res.snippet,
            engine=res.engine,
            trust_tier=_tier_for_url(res.url),
        )
        for res in results
    ]

    inserted = session.add_sources(cards)
    session.search_calls += 1

    output = [f"Academic search found {len(results)} results ({len(inserted)} new):"]
    for src in inserted[:8]:
        output.append(
            f"{src.id}: {src.title} ({src.url}) "
            f"trust={src.trust_tier} snippet={src.snippet[:240]}"
        )
    
    return "\n".join(output)
