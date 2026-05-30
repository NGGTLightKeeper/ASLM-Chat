# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
import re
from typing import Any


_SPACE_RE = re.compile(r"\s+")
_EFFORT_VALUES = ("low", "medium", "high")
_EFFORT_ALIASES = {
    "": "medium",
    "normal": "medium",
    "default": "medium",
    "standard": "medium",
}

WebSearchQuery = str | dict[str, Any]

SEARCH_QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "query": {
            "type": "string",
            "minLength": 1,
            "maxLength": 220,
            "description": (
                "Plain web search query. Keep it short and specific: concrete names, identifiers, "
                "version numbers, exact error text, or explicit constraints. Do not write a full "
                "sentence, explanation, or SEO-style keyword pile."
            ),
        },
        "effort": {
            "type": "string",
            "enum": list(_EFFORT_VALUES),
            "default": "medium",
            "description": (
                "Search effort level. low is fast and mostly snippet-based; medium is the "
                "current default; high expands the current search and scraping budget."
            ),
        },
    },
    "required": ["query"],
}


# Normalize the public search effort argument.
def coerce_search_effort(value: Any = None) -> str:
    if isinstance(value, dict):
        value = value.get("effort")
    elif isinstance(value, str):
        parsed = _try_parse_json(value)
        if isinstance(parsed, dict):
            value = parsed.get("effort")

    effort = str(value or "").strip().lower()
    effort = _EFFORT_ALIASES.get(effort, effort)
    return effort if effort in _EFFORT_VALUES else "medium"


# Convert the public query argument into one provider-ready search string.
def coerce_search_query(value: Any) -> str:
    if isinstance(value, dict):
        plan = value.get("query", value)
        if isinstance(plan, str):
            return sanitize_legacy_query(plan)
        # Structured search plans did not work; models used them to make worse queries.
        for key in ("raw_query", "q", "text"):
            if isinstance(plan.get(key), str):
                return sanitize_legacy_query(plan[key])
        return ""

    if isinstance(value, str):
        parsed = _try_parse_json(value)
        if isinstance(parsed, dict):
            legacy = coerce_search_query(parsed)
            if legacy:
                return legacy
        return sanitize_legacy_query(value)

    return sanitize_legacy_query(str(value or ""))


# Collapse whitespace and cap legacy free-text queries at 220 characters.
def sanitize_legacy_query(query: str) -> str:
    text = str(query or "").strip()
    text = text.replace("\r", " ").replace("\n", " ")
    return _SPACE_RE.sub(" ", text).strip()[:220].strip()


# Best-effort JSON parse for string tool arguments that look like objects.
def _try_parse_json(value: str) -> Any:
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        return json.loads(stripped)
    except Exception:
        return None
