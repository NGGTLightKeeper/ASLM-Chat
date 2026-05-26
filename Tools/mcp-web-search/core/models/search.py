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
    excluded_domains: list[str] = field(default_factory=list)
    # Hint for provider selection: "ddgs" | "auto"
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
    # Originating engine identifier, e.g. "ddgs:google,brave", "brave", "tavily"
    engine: str = ""
    # Trust tier from domain registry: "friendly" | "moderate" | "hardened" | "fortress" | "?"
    trust_tier: str = "?"
    # Internal relevance score assigned by the service layer
    score: float = 0.0
    # Optional opaque hint forwarded to the extraction layer
    method_hint: str = ""
    # Publication date as provided by the search engine (raw string, engine-dependent format)
    published_date: str = ""
    # Direct PDF URL when the source page or engine exposes one.
    pdf_url: str = ""
    # Debugging fields (filled by service layer, stripped in MCP adapter)
    extract_debug_stage: str = ""
    extract_debug_timeout_sec: float = 0.0
    # Neural/routing debug fields (internal; stripped by adapters unless copied explicitly)
    snippet_relevance_score: float = 0.0
    parsed_relevance_score: float = 0.0
    routing_score: float = 1.0
    routing_debug: dict = field(default_factory=dict)


@dataclass
class SearchSource:
    """UI/model-facing representation of one ranked search source."""

    id: str
    rank: int
    title: str
    url: str
    domain: str
    display_domain: str
    favicon_url: str
    snippet: str
    preview: str = ""
    published_date: str = ""
    engine: str = ""
    trust_tier: str = "?"
    score: float = 0.0
    pdf_url: str = ""


@dataclass
class SearchRichResult:
    """Structured web-search payload shared by model context and UI."""

    query: str
    search_id: str
    sources: list[SearchSource]
    model_context: str
    ui: dict[str, object] = field(default_factory=dict)
