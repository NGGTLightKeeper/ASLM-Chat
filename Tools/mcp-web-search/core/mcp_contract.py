# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Model-facing MCP contract for the search tools (ported from the legacy adapter).

Two things the model sees: the parameter SCHEMA and the tool DESCRIPTIONS. Both are
instructions, not mechanics — the model is told *how to drive* the tool, never how the
pipeline works internally. The schema is deliberately minimal: the model controls only
the query, the effort, and the shopping opt-in. Region routing, recency/timelimit (parsed
from the query), safe-search and engine selection are all decided internally and are not
model-facing knobs.
"""

from __future__ import annotations

import json
import re
from typing import Any

_SPACE_RE = re.compile(r"\s+")
_EFFORT_VALUES = ("low", "medium", "high")
_EFFORT_ALIASES = {"": "medium", "normal": "medium", "default": "medium", "standard": "medium"}

MCP_SERVER_DESCRIPTION = "Search and page-reading tools."


WEB_SEARCH_TOOL_DESCRIPTION = """\
Ranked web search with optional page-content extraction.

The query is a search-engine directive, not a conversational request. Write it like a
librarian's search expression: concrete nouns, identifiers, versions, quoted error text,
and at most one intent term — no prose, no questions, no explanation.

EFFORT — pick the LOWEST tier that can answer; escalate on evidence, never by default:
  effort="low"     Fast discovery. SERP only — no page scraping. Use for quick source
                   discovery, names, URLs, and rough orientation.
  effort="medium"  Default and starting point for every new intent. Ranks results and
                   parses a few top pages into previews. Use first for ordinary cited
                   answers, comparisons, reviews, and how-tos. Open here unless you
                   already hold a medium/low result for this exact intent that fell short.
  effort="high"    GATED RESERVE TIER — not a quality dial. Larger source pool and deeper
                   parsing, reserved for when normal search has already failed you. Before
                   a high call is allowed, ALL THREE must hold:
                     (a) you already ran medium (or low) on this SAME intent earlier in
                         this response, AND
                     (b) that result left a specific claim unresolved that you can name in
                         one sentence, AND
                     (c) the gap is high-stakes or the task is genuinely exhaustive.
                   If you cannot name the prior call and the exact unresolved claim, you do
                   not meet the bar → use medium. NEVER open an intent at high. NEVER make
                   high your first search. After a high call, do not re-run the same intent
                   at a lower effort — answer from the evidence collected.

ESCALATION BUDGET — high is rationed:
  You may issue at most 3 high calls per response. Any high call beyond that returns a
  quota notice instead of results and burns the turn. Treat high as a red button, not a
  routine. If a high call ever returns a quota / "unavailable" notice, IMMEDIATELY
  downshift the remaining searches to medium or low — do not re-issue high. Before each
  high call, confirm you still have budget AND a concrete, nameable reason; if either is
  missing, run medium.

SUFFICIENCY — before issuing ANY further search (any tier), check whether the evidence
already in hand answers the request. If it does, stop searching and write the answer. Do
not open an adjacent sub-topic at high just because it is related — escalate only on a gap
you can name, and only after medium on that sub-topic has actually fallen short.

SHOPPING:
  shopping=false   Default. Never runs shopping providers.
  shopping=true    Use only when the user needs a specific product, its price, where to
                   buy it, or availability. The query must be only the search subject
                   (model, spec, SKU, or product phrase) — no questions, no filler. Keep
                   false for technical meanings such as payload delivery or supply chain.

ACADEMIC:
  academic=false   Default. Never runs scholarly providers.
  academic=true    Use when the user needs peer-reviewed papers, preprints, citations, or
                   primary scientific literature — not popular articles or how-tos. Adds
                   structured results (title, authors, year, DOI, abstract, PDF) from open
                   scholarly indexes (OpenAlex, Crossref, Europe PMC, DOAJ, arXiv). The
                   query should be the topic/title/author/DOI, not a question.

OPERATORS (ASCII only — never translate):
  site:domain.com        restrict to a domain and its subdomains
  -site:domain.com       exclude a domain
  "exact phrase"         force an exact match; counts as one content token
  term1 OR term2         either term
  - "reddit"/"github"/"arxiv" are keywords, not constraints — use site:reddit.com etc.
  - Always quote exact error text: "ModuleNotFoundError: No module named 'x'"

LAYERED QUERIES — only when the first result leaves a distinct claim unresolved:
  1. Find the exact name/version:  pytorch 2.3 release
  2. Drill in:  "torch.compile" python 3.12 site:github.com
  3. Cross-check:  torch.compile site:pytorch.org
  Stop as soon as the request is answerable; do not run every layer by default.

CITATION:
  - Cite only with the exact handles returned in the search context.
  - Place each handle immediately after the sentence it supports.
  - Cite a source only when its content explicitly confirms the claim.
  - Never reuse handles from a different query or an earlier call; never invent them.
  - Parsed content outweighs snippet-only sources.

LANGUAGE: search in English by default; use a local language only for region-specific
sources or proper names that exist only in that language."""


READ_PAGE_TOOL_DESCRIPTION = """\
Open one or more URLs and extract the readable text as markdown.

Use it when you need:
- the full content of an article, documentation page, post, or thread;
- cleaner text after search surfaced promising URLs;
- a small batch read of several shortlisted pages (pass a list of URLs).

It works best as the second step after search, once discovery is done and you want to
read the sources. PDFs, YouTube transcripts, Reddit threads, GitHub pages, StackExchange
questions, and X/Twitter posts are handled automatically from their URL."""


SEARCH_QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "query": {
            "type": "string",
            "minLength": 1,
            "maxLength": 220,
            "description": (
                "Plain web search query. Keep it short and specific: concrete names, "
                "identifiers, version numbers, exact error text, or explicit constraints. "
                "Do not write a full sentence, a question, or an SEO-style keyword pile."
            ),
        },
        "effort": {
            "type": "string",
            "enum": list(_EFFORT_VALUES),
            "default": "medium",
            "description": (
                "Search effort — pick the lowest tier that can answer. low: fast, "
                "SERP-only discovery. medium (default): ranks and parses a few top pages; "
                "the starting point for every new intent. high: rationed reserve tier "
                "(max 3 per response — excess high calls return a quota notice, not "
                "results). high is allowed ONLY after a medium/low call on the SAME intent "
                "left a specific, nameable claim unresolved AND the gap is high-stakes; "
                "never as the first search for an intent, never as a quality dial. On a "
                "quota notice, downshift remaining searches to medium or low."
            ),
        },
        "shopping": {
            "type": "boolean",
            "default": False,
            "description": (
                "Enable shopping providers and structured product/price results. Set true "
                "only when the user needs a specific product, its price, where to buy it, "
                "or availability; the query must then be only the search subject (model, "
                "spec, SKU, product phrase). Leave false for all other searches."
            ),
        },
        "academic": {
            "type": "boolean",
            "default": False,
            "description": (
                "Enable scholarly providers and structured paper results (title, authors, "
                "year, DOI, abstract, PDF) from open indexes (OpenAlex, Crossref, Europe "
                "PMC, DOAJ, arXiv). Set true only when the user needs peer-reviewed papers, "
                "preprints, citations, or primary scientific literature; the query should "
                "be the topic, title, author, or DOI. Leave false for all other searches."
            ),
        },
    },
    "required": ["query"],
}


# The onion opt-in property — added to the schema ONLY when the tor path is enabled in
# config, so the model never sees an argument it cannot use.
_ONION_PROPERTY: dict[str, Any] = {
    "type": "boolean",
    "default": False,
    "description": (
        "Enable censorship-resistant onion sources over Tor (vetted allowlist: news "
        "SecureDrop/onion mirrors, rights orgs, privacy services). Set true only when the "
        "user explicitly needs Tor/onion access or is working around blocking; it is slow "
        "(Tor latency) and off-topic for ordinary searches. Leave false otherwise."
    ),
}


# Build the search tool's input schema for the current config. The onion opt-in is exposed
# only while tor.enabled, so the advertised arguments track the actual capability.
def build_search_schema() -> dict[str, Any]:
    import copy

    schema = copy.deepcopy(SEARCH_QUERY_SCHEMA)
    try:
        from core.config import load_search_config

        if load_search_config().tor.enabled:
            schema["properties"]["onion"] = dict(_ONION_PROPERTY)
    except Exception:  # noqa: BLE001 — config trouble must never break tool registration
        pass
    return schema


# Best-effort JSON parse for string tool arguments that look like objects.
def _try_parse_json(value: str) -> Any:
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        return json.loads(stripped)
    except Exception:  # noqa: BLE001
        return None


# Collapse whitespace and cap a free-text query at 220 characters.
def sanitize_query(query: str) -> str:
    text = str(query or "").strip().replace("\r", " ").replace("\n", " ")
    return _SPACE_RE.sub(" ", text).strip()[:220].strip()


# Convert the public query argument (string or {query|raw_query|q|text: ...}) into one
# provider-ready search string.
def coerce_search_query(value: Any) -> str:
    if isinstance(value, dict):
        plan = value.get("query", value)
        if isinstance(plan, str):
            return sanitize_query(plan)
        if isinstance(plan, dict):
            for key in ("raw_query", "q", "text"):
                if isinstance(plan.get(key), str):
                    return sanitize_query(plan[key])
        return ""
    if isinstance(value, str):
        parsed = _try_parse_json(value)
        if isinstance(parsed, dict):
            nested = coerce_search_query(parsed)
            if nested:
                return nested
        return sanitize_query(value)
    return sanitize_query(str(value or ""))


# Normalize the public effort argument to one of low/medium/high (default medium).
def coerce_search_effort(value: Any = None) -> str:
    if isinstance(value, dict):
        value = value.get("effort")
    elif isinstance(value, str):
        parsed = _try_parse_json(value)
        if isinstance(parsed, dict):
            value = parsed.get("effort")
    effort = _EFFORT_ALIASES.get(str(value or "").strip().lower(), str(value or "").strip().lower())
    return effort if effort in _EFFORT_VALUES else "medium"


# Normalize an explicit boolean opt-in argument (shopping / academic) to a bool.
def _coerce_bool_opt(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        value = value.get(key, False)
    elif isinstance(value, str):
        parsed = _try_parse_json(value)
        if isinstance(parsed, dict):
            value = parsed.get(key, False)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value) if isinstance(value, (int, float)) else False


# Normalize the explicit shopping opt-in argument to a bool.
def coerce_search_shopping(value: Any = None) -> bool:
    return _coerce_bool_opt(value, "shopping")


# Normalize the explicit academic opt-in argument to a bool.
def coerce_search_academic(value: Any = None) -> bool:
    return _coerce_bool_opt(value, "academic")


# Normalize the onion opt-in, AND-gated on the tor capability: even if a caller passes
# onion=true, it is honored only when tor.enabled — so the intent flag can never activate
# the path while the capability is off (double-guards a stale/cached schema).
def coerce_search_onion(value: Any = None) -> bool:
    if not _coerce_bool_opt(value, "onion"):
        return False
    try:
        from core.config import load_search_config

        return bool(load_search_config().tor.enabled)
    except Exception:  # noqa: BLE001
        return False
