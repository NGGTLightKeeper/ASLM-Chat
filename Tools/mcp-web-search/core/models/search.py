# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Search domain models.

Defines the canonical data contracts for web search results
and query routing hints. All services must produce/consume these types.

Public API
----------
SearchResult   -- one result from any search provider
QueryPlan      -- a search query with routing hints
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Query planning
# ---------------------------------------------------------------------------

@dataclass
class QueryPlan:
    """Store a search query together with routing hints."""

    query: str
    target_domains: list[str] = field(default_factory=list)
    # Hint for provider selection: "ddgs" | "yacy" | "auto"
    method_hint: str = "auto"


# ---------------------------------------------------------------------------
# Search result
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    """Represent one search result returned by any backend."""

    url: str
    title: str
    snippet: str
    # Originating engine identifier, e.g. "ddgs:google,brave", "yacy_global"
    engine: str = ""
    # Trust tier from domain registry: "friendly" | "moderate" | "hardened" | "fortress" | "?"
    trust_tier: str = "?"
    # Internal relevance score assigned by the service layer
    score: float = 0.0
    # Optional opaque hint forwarded to the extraction layer
    method_hint: str = ""
    # Debugging fields (filled by service layer, stripped in MCP adapter)
    extract_debug_stage: str = ""
    extract_debug_timeout_sec: float = 0.0
