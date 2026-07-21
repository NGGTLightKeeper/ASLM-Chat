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

from core.query.search_plan import (
    PlanValidationError,
    build_advanced_search_schema,
    prepare_advanced_search,
)

_SPACE_RE = re.compile(r"\s+")
_EFFORT_VALUES = ("low", "medium", "high")
_EFFORT_ALIASES = {"": "medium", "normal": "medium", "default": "medium", "standard": "medium"}
SEARCH_BATCH_LIMIT = 3

MCP_SERVER_DESCRIPTION = "Search and page-reading tools."


LEGACY_WEB_SEARCH_TOOL_DESCRIPTION = """\
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
  -term                  exclude a noisy or ambiguous meaning
  filetype:pdf           restrict results to a file type
  intitle:term           require a term or quoted phrase in the page title
  inurl:term             require a term in the URL
  before:YYYY-MM-DD      results published before a date
  after:YYYY-MM-DD       results published after a date
  - "reddit"/"github"/"arxiv" are keywords, not constraints — use site:reddit.com etc.
  - Always quote exact error text: "ModuleNotFoundError: No module named 'x'"

OPERATOR EXAMPLES:
  Exact phrase or error:  "CUDA out of memory" pytorch
  Either spelling:        postgresql OR postgres deadlock
  Remove an ambiguity:    jaguar speed -car -automotive
  PDF documents:          EU AI Act implementation filetype:pdf
  Page title:             intitle:"release notes" pytorch 2.3
  URL text:               kubernetes scheduler inurl:issues
  Date range:             OpenAI API pricing after:2026-01-01 before:2026-07-01
  One specific source:    wireguard android battery site:reddit.com

BATCH SEARCH:
  A plain string is the default. Use an array only for 2-3 independently necessary
  deliverables, never for synonyms, broad/narrow variants, candidate names, domains,
  speculative follow-ups, or fallback attempts. If two items would support the same
  claim, keep only the stronger one. Inspect one result set before issuing a refinement.
  When those conditions are met, pass query as an array of strings.
  Every array item has its own source allowance: low returns up to 8 sources per item,
  medium up to 10, and high up to 16. Thus three medium items can produce up to 30 source
  records before URL deduplication and filtering. Never batch to inflate source count.

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


ADVANCED_WEB_SEARCH_TOOL_DESCRIPTION = """\
Ranked web search with optional page-content extraction.

Submit a structured plan in queries. Each item is one independently useful search with:
- purpose: a short human-readable reason for the query;
- vertical: web, shopping, academic, or onion when that capability is advertised;
- text: a concise search body without operators;
- operators: typed search constraints compiled by the backend.

One query is the default. Do not batch synonyms, broad/narrow variants of one intent,
candidate names, domains, speculative follow-ups, or fallback attempts. Use OR for true
alternatives and inspect the first result set before refining. A batch is justified only
when the request already has multiple independently necessary deliverables that support
different claims or require different verticals. If two items would support the same
sentence, keep only the stronger one. Two queries should cover almost every valid batch;
three or four are exceptional and require three or four distinct deliverables.

Select shopping only for price or availability work; use web for independent sources and
currency conversion. Source allowances apply to EACH query: low returns up to 8 sources,
medium up to 10, and high up to 16. A four-item medium batch may therefore produce up to
40 source records before URL deduplication and filtering, consuming far more context than
one query. Never batch merely to collect more sources.

Operator fields map deterministically to exact phrases, OR alternatives, excluded terms,
site inclusion/exclusion, file types, title terms, URL terms, and before/after dates. Never
write those operators inside text and never put several searches into one text value.

Use effort=medium first. low is SERP-only discovery. high is a gated reserve tier and may
be used only after a lower-effort search left a specific high-stakes claim unresolved.

Cite only exact handles returned by this call, immediately after the claim they support.
Do not reuse handles from earlier calls. Prefer parsed page content over snippets. Search
in English by default and use a local language only for region-specific sources."""

# Compatibility export for callers that do not use the config-aware builder.
WEB_SEARCH_TOOL_DESCRIPTION = ADVANCED_WEB_SEARCH_TOOL_DESCRIPTION


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
            "oneOf": [
                {"type": "string", "minLength": 1, "maxLength": 220},
                {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": SEARCH_BATCH_LIMIT,
                    "items": {"type": "string", "minLength": 1, "maxLength": 220},
                },
            ],
            "description": (
                "One plain web search query, or an array of up to 3 closely related queries "
                "to run concurrently. Keep each query short and specific: concrete names, "
                "identifiers, version numbers, exact error text, or explicit constraints. "
                "Use site:domain.com for a source restriction, not a bare service name. "
                "Do not write a full sentence, a question, an SEO-style keyword pile, or a "
                "comma-separated batch."
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
def search_schema_mode() -> str:
    try:
        from core.config import load_search_config

        mode = str(load_search_config().query.schema_mode or "advanced").strip().lower()
    except Exception:  # noqa: BLE001
        mode = "advanced"
    return mode if mode in {"legacy", "advanced"} else "advanced"


def search_ui_display_mode() -> str:
    try:
        from core.config import load_search_config

        mode = str(
            getattr(load_search_config().query, "ui_display_mode", "compiled_query")
            or "compiled_query"
        ).strip().lower()
    except Exception:  # noqa: BLE001
        mode = "compiled_query"
    return mode if mode in {"purpose", "compiled_query"} else "compiled_query"


def build_search_description() -> str:
    return (
        LEGACY_WEB_SEARCH_TOOL_DESCRIPTION
        if search_schema_mode() == "legacy"
        else ADVANCED_WEB_SEARCH_TOOL_DESCRIPTION
    )


def build_search_schema() -> dict[str, Any]:
    import copy

    try:
        from core.config import load_search_config

        tor_enabled = bool(load_search_config().tor.enabled)
    except Exception:  # noqa: BLE001
        tor_enabled = False

    if search_schema_mode() == "advanced":
        return build_advanced_search_schema(tor_enabled=tor_enabled)

    schema = copy.deepcopy(SEARCH_QUERY_SCHEMA)
    if tor_enabled:
        schema["properties"]["onion"] = dict(_ONION_PROPERTY)
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


# Convert the public query argument into one to three provider-ready search strings.
def coerce_search_queries(value: Any, *, limit: int = SEARCH_BATCH_LIMIT) -> list[str]:
    limit = max(1, int(limit or SEARCH_BATCH_LIMIT))
    if isinstance(value, dict):
        plan = value.get("query", value)
        if isinstance(plan, dict):
            for key in ("raw_query", "q", "text"):
                if key in plan:
                    return coerce_search_queries(plan[key], limit=limit)
            return []
        return coerce_search_queries(plan, limit=limit)
    if isinstance(value, (list, tuple)):
        queries: list[str] = []
        for item in value:
            query = sanitize_query(item)
            if query:
                queries.append(query)
            if len(queries) >= limit:
                break
        return queries
    if isinstance(value, str):
        parsed = _try_parse_json(value)
        if isinstance(parsed, (dict, list)):
            nested = coerce_search_queries(parsed, limit=limit)
            if nested:
                return nested
        query = sanitize_query(value)
        return [query] if query else []
    query = sanitize_query(str(value or ""))
    return [query] if query else []


# Backwards-compatible single-query helper for older callers.
def coerce_search_query(value: Any) -> str:
    queries = coerce_search_queries(value, limit=1)
    return queries[0] if queries else ""


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


def _public_search_request(request: dict[str, Any]) -> dict[str, Any]:
    public = {key: value for key, value in request.items() if key != "queries"}
    public["queries"] = [
        {key: value for key, value in query.items() if key != "timelimit"}
        for query in request.get("queries", [])
        if isinstance(query, dict)
    ]
    return public


def invalid_search_plan_result(issues: list[dict[str, str]]) -> dict[str, Any]:
    details = "; ".join(
        f"{issue.get('path', '$')}: {issue.get('message', 'invalid value')}"
        for issue in issues
    )
    message = f"INVALID_SEARCH_PLAN: {details}"
    return {
        "error": {"code": "INVALID_SEARCH_PLAN", "issues": issues},
        "sources": [],
        "model_context": message,
        "ui": {
            "kind": "web_search",
            "status": "rejected",
            "query_display_mode": search_ui_display_mode(),
            "result_count": 0,
            "query_count": 0,
            "error": {"code": "INVALID_SEARCH_PLAN", "issues": issues},
        },
    }


def prepare_search_arguments(arguments: Any) -> dict[str, Any]:
    """Return canonical arguments and normalized UI data before network work."""

    if search_schema_mode() == "advanced":
        try:
            from core.config import load_search_config

            cfg = load_search_config()
            prepared = prepare_advanced_search(
                arguments,
                query_config=cfg.query,
                tor_enabled=bool(cfg.tor.enabled),
            )
        except PlanValidationError as exc:
            error_result = invalid_search_plan_result(exc.issues)
            return {
                "ok": False,
                "arguments": {},
                "tool_ui": error_result["ui"],
                "error_result": error_result,
            }
        request = _public_search_request(prepared["search_request"])
        return {
            "ok": True,
            "arguments": prepared["canonical_arguments"],
            "search_request": prepared["search_request"],
            "tool_ui": {
                "kind": "web_search",
                "status": "pending",
                "query_display_mode": search_ui_display_mode(),
                "query_count": len(request["queries"]),
                "search_request": request,
            },
        }

    args = arguments if isinstance(arguments, dict) else {}
    queries = coerce_search_queries(args.get("query", ""))
    canonical_query: str | list[str] = queries[0] if len(queries) == 1 else queries
    effort = coerce_search_effort(args)
    shopping = coerce_search_shopping(args)
    academic = coerce_search_academic(args)
    onion = coerce_search_onion(args)
    canonical: dict[str, Any] = {
        "query": canonical_query,
        "effort": effort,
        "shopping": shopping,
        "academic": academic,
    }
    if onion:
        canonical["onion"] = True
    vertical = "shopping" if shopping else ("academic" if academic else ("onion" if onion else "web"))
    request = {
        "schema_mode": "legacy",
        "effort": effort,
        "queries": [
            {
                "purpose": "",
                "vertical": vertical,
                "compiled_query": query,
                "operators": {},
            }
            for query in queries
        ],
    }
    return {
        "ok": True,
        "arguments": canonical,
        "search_request": request,
        "tool_ui": {
            "kind": "web_search",
            "status": "pending",
            "query_display_mode": search_ui_display_mode(),
            "query_count": len(queries),
            "search_request": request,
        },
    }
