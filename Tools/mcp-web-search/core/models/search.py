# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from dataclasses import dataclass, field


# Store a search query together with routing hints.
@dataclass
class QueryPlan:
    query: str
    target_domains: list[str] = field(default_factory=list)
    excluded_domains: list[str] = field(default_factory=list)
    # Hint for provider selection: "ddgs" | "auto"
    method_hint: str = "auto"


# Represent one search result returned by any backend.
@dataclass
class SearchResult:
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
    # Full text payload exposed by hosted providers; used internally for preview extraction.
    provider_content: str = ""
    # Debugging fields (filled by service layer, stripped in MCP adapter)
    extract_debug_stage: str = ""
    extract_debug_timeout_sec: float = 0.0
    # Neural/routing debug fields (internal; stripped by adapters unless copied explicitly)
    snippet_relevance_score: float = 0.0
    parsed_relevance_score: float = 0.0
    routing_score: float = 1.0
    routing_debug: dict = field(default_factory=dict)


# UI/model-facing representation of one ranked search source.
@dataclass
class SearchSource:
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


# Structured web-search payload shared by model context and UI.
@dataclass
class SearchRichResult:
    query: str
    search_id: str
    sources: list[SearchSource]
    model_context: str
    ui: dict[str, object] = field(default_factory=dict)
