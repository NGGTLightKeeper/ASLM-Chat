# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Site mapping tool for deep research."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from core.mappers.site_mapper import SiteMapper
from services.deep_research.models import SourceCard

if TYPE_CHECKING:
    from services.deep_research.models import ResearchSession

logger = logging.getLogger("services.deep_research.tools.site_mapper")

async def run_agent_site_map(
    session: ResearchSession,
    url: str,
    topic: str,
) -> str:
    """Execute site mapping and update source pool with relevant nodes."""
    cache = None
    try:
        from services.web_search import _cache as _web_cache
        cache = _web_cache
    except Exception:
        pass

    budget_sec = float(getattr(session.config, "search_timeout_sec", 30.0))
    mapper = SiteMapper(time_budget_sec=budget_sec, max_nodes=10, cache=cache)
    result = await mapper.map_domain(url, topic)
    
    nodes = result.get("nodes", {})
    session.site_map_calls += 1  # count regardless of result so hard cap fires on empty domains too
    if not nodes:
        return f"Smart mapper found no relevant nodes on {url} for topic: {topic}"
    
    cards = [
        SourceCard(
            id="",
            url=u,
            title=d["title"],
            snippet=d["snippet"],
            engine="academic:site_map",
            score=d["score"],
            trust_tier="moderate",
        )
        for u, d in nodes.items()
        if u != url  # Don't re-add the start URL as a new discovery
    ]
    
    inserted = session.add_sources(cards)

    output = [f"Smart mapper explored {url} and found {len(nodes)} relevant nodes ({len(inserted)} new):"]
    for u, d in list(nodes.items())[:5]:
        output.append(f"- {d['title']} (Score: {d['score']})")
        output.append(f"  URL: {u}")
    
    return "\n".join(output)
