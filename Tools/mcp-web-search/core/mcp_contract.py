# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Model-facing MCP contract for the search tools (ported from the legacy adapter).

The model sees a config-selected parameter schema and matching tool description. Legacy
keeps its compact query flags; advanced exposes a typed mixed-vertical plan compiled by
one backend path. Region routing, safe-search, and engine selection remain internal.
"""

from __future__ import annotations

import json
import re
from typing import Any

from core.query.search_plan import (
    PlanValidationError,
    VERTICAL_QUERY_LIMITS,
    build_advanced_search_schema,
    prepare_advanced_search,
)

_SPACE_RE = re.compile(r"\s+")
_EFFORT_VALUES = ("low", "medium", "high")
_EFFORT_ALIASES = {"": "medium", "normal": "medium", "default": "medium", "standard": "medium"}
SEARCH_BATCH_LIMIT = VERTICAL_QUERY_LIMITS["web"]
LEGACY_BATCH_LIMIT = max(
    VERTICAL_QUERY_LIMITS[vertical] for vertical in ("web", "shopping", "academic")
)

MCP_SERVER_DESCRIPTION = "Search and page-reading tools."


LEGACY_WEB_SEARCH_TOOL_DESCRIPTION = """\
Ranked web search with optional page-content extraction.

For every non-atomic research task, make an internal plan before calling this tool. Define
answer deliverables, evidence gaps, source classes, vertical or controls, query anchors,
operator purposes, dependencies, and success conditions. Each call executes the next plan
step; inspect its evidence and update the plan before continuing. Link count alone is not
coverage when the sources all belong to one class.

Write a compact search expression built from concrete entities, identifiers, versions,
and one intent term. A plain query string is the normal form. Arrays are reserved for
independently necessary deliverables with distinct evidence targets. Every vertical permits
at most 2 queries per call; alternatives for one claim fit one query through OR. These are
ceilings, not targets.

Use the least constrained query that can identify the target. Stacking near-synonyms,
several exact phrases, broad OR groups, and site/date restrictions can hide valid results
even from Google. Every operator must remove a known ambiguity or enforce an answer-critical
boundary. After an empty or weak result, simplify first: remove redundant words, phrases,
and alternatives while retaining only essential constraints; do not respond by adding more.

Use ASCII operators when they express a real constraint: quoted phrases, OR, -term,
site:, -site:, filetype:, intitle:, inurl:, after:, and before:. Date bounds fit requests
whose answer materially depends on a publication window. Keep four-digit calendar years
out of the query body; a necessary year belongs exclusively inside after: or before:.
Examples: `postgresql OR postgres deadlock`, `report filetype:pdf`,
`intitle:"release notes" runtime`, and `api changes site:docs.example.com`.

The specialized controls are required routing, not reserve options. Set shopping=true for
product discovery, budgets, prices, sellers, stock, or availability. Set academic=true for
papers, citations, DOI records, preprints, peer-reviewed support, or primary scientific
literature. Use ordinary web search separately for official pages, independent reviews,
reporting, communities, measurements, and currency references. Start ordinary work at
medium; low is quick discovery and high is the reserve tier after a lower-effort result
leaves a concrete high-stakes gap.

Source allowance is per query: low up to 8, medium up to 10, high up to 16 before URL
deduplication and filtering. Context cost scales with every query.

Cite the exact handles returned by this call immediately after the supported claim.
Parsed page content carries more weight than snippets. English is the normal search
language; regional evidence and local proper names benefit from the matching language."""


ADVANCED_WEB_SEARCH_TOOL_DESCRIPTION = """\
Ranked web search with optional page-content extraction.

Choose the query field by evidence type. MUST use `shopping` for products, prices, sellers,
stock, availability, delivery, and purchase options. MUST use `academic` for papers, citations,
DOI records, preprints, and primary research. Use `web` for official, independent, community,
news, measurement, and general evidence, but never as a substitute for shopping or academic.
Use `onion` only when that advertised field is available and Tor access is explicitly needed.

Each vertical field accepts one query string. Batch only when two independent evidence gaps
are both needed: either pass an array of two strings in one vertical field, or pass one string
in each of two vertical fields. Never submit more than two queries total. High effort never
batches: when multiple queries are supplied with high, only the first is executed and the
result warns that the rest were skipped.

`call_description` is only the visible UI description of this tool invocation. It is not a
query and never replaces one. The selected vertical field is the only place for the complete
search text and must never be empty. Put compact terms and any needed search operators there.

Start ordinary work at medium. Use low for quick discovery and high only after a lower-effort
search leaves a specific high-stakes gap. After weak results, simplify the query before adding
constraints. Cite exact source handles returned by the tool."""

# Compatibility export for callers that do not use the config-aware builder.
WEB_SEARCH_TOOL_DESCRIPTION = ADVANCED_WEB_SEARCH_TOOL_DESCRIPTION


READ_PAGE_TOOL_DESCRIPTION = """\
Open one or more URLs and extract the readable text as markdown.

The `url` input must contain an exact, non-empty URL. Never call this with an empty value or
a search topic. If no exact URL is available yet, call web_search first.

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
                    "maxItems": LEGACY_BATCH_LIMIT,
                    "items": {"type": "string", "minLength": 1, "maxLength": 220},
                },
            ],
            "description": (
                "One plain search query, or an array of independently necessary queries to run "
                "concurrently. Every vertical permits at most 2 queries per call. "
                "Keep each query short and specific: concrete names, "
                "identifiers, version numbers, exact error text, or explicit constraints. "
                "Four-digit calendar years are forbidden as content tokens; place a "
                "necessary year only inside after: or before:. "
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
                "Required routing for product discovery, budgets, prices, sellers, stock, "
                "availability, and purchase options. Set true whenever the evidence gap "
                "contains any of those needs; keep the query to the product, model, spec, "
                "SKU, or product phrase. Use a separate ordinary web search for reviews."
            ),
        },
        "academic": {
            "type": "boolean",
            "default": False,
            "description": (
                "Required routing for papers, authors, citations, DOI records, preprints, "
                "peer-reviewed support, scholarly consensus, and primary scientific "
                "literature. Set true whenever the evidence gap contains any of those "
                "needs; query by topic, title, author, or DOI."
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


# Convert the public query argument into provider-ready search strings up to the supplied limit.
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


def _search_query_item_count(value: Any) -> int:
    if isinstance(value, dict):
        plan = value.get("query", value)
        if isinstance(plan, dict):
            for key in ("raw_query", "q", "text"):
                if key in plan:
                    return _search_query_item_count(plan[key])
            return 0
        return _search_query_item_count(plan)
    if isinstance(value, (list, tuple)):
        return len(value)
    if isinstance(value, str):
        parsed = _try_parse_json(value)
        if isinstance(parsed, (dict, list)):
            return _search_query_item_count(parsed)
        return 1 if value.strip() else 0
    return 1 if value is not None and str(value).strip() else 0


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


def invalid_search_plan_result(
    issues: list[dict[str, str]], *, description: str = ""
) -> dict[str, Any]:
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
            "description": sanitize_query(description)[:80],
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
            raw_description = (
                arguments.get("call_description", "") if isinstance(arguments, dict) else ""
            )
            error_result = invalid_search_plan_result(
                exc.issues,
                description=raw_description if isinstance(raw_description, str) else "",
            )
            return {
                "ok": False,
                "arguments": {},
                "tool_ui": error_result["ui"],
                "error_result": error_result,
            }
        request = _public_search_request(prepared["search_request"])
        warnings = list(prepared.get("warnings") or [])
        return {
            "ok": True,
            "arguments": prepared["canonical_arguments"],
            "search_request": prepared["search_request"],
            "warnings": warnings,
            "tool_ui": {
                "kind": "web_search",
                "status": "pending",
                "description": request["description"],
                "query_count": len(request["queries"]),
                "search_request": request,
                **({"warnings": warnings} if warnings else {}),
            },
        }

    args = arguments if isinstance(arguments, dict) else {}
    raw_query = args.get("query", "")
    shopping = coerce_search_shopping(args)
    academic = coerce_search_academic(args)
    onion = coerce_search_onion(args)
    vertical = "shopping" if shopping else ("academic" if academic else ("onion" if onion else "web"))
    query_limit = VERTICAL_QUERY_LIMITS[vertical]
    query_count = _search_query_item_count(raw_query)
    if query_count > query_limit:
        error_result = invalid_search_plan_result(
            [
                {
                    "path": "$.query",
                    "message": f"{vertical} permits at most {query_limit} queries per call",
                }
            ]
        )
        return {
            "ok": False,
            "arguments": {},
            "tool_ui": error_result["ui"],
            "error_result": error_result,
        }
    queries = coerce_search_queries(raw_query, limit=query_limit)
    canonical_query: str | list[str] = queries[0] if len(queries) == 1 else queries
    effort = coerce_search_effort(args)
    canonical: dict[str, Any] = {
        "query": canonical_query,
        "effort": effort,
        "shopping": shopping,
        "academic": academic,
    }
    if onion:
        canonical["onion"] = True
    request = {
        "schema_mode": "legacy",
        "effort": effort,
        "queries": [
            {
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
            "query_count": len(queries),
            "search_request": request,
        },
    }
