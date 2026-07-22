# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Strict, deterministic preparation of advanced web-search plans."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any
from urllib.parse import urlsplit

from core.query.operators import (
    SEARCH_OPERATOR_BY_KEY,
    SEARCH_OPERATOR_SPECS,
    SearchOperatorSpec,
    has_search_operators,
)
from core.search.query_dates import resolve_query_dates


ADVANCED_BATCH_LIMIT = 4
ADVANCED_TEXT_LIMIT = 160
COMPILED_QUERY_LIMIT = 512
DESCRIPTION_LIMIT = 80
_EFFORTS = ("low", "medium", "high")
_BASE_VERTICALS = ("web", "shopping", "academic")
_OPERATOR_KEYS = tuple(SEARCH_OPERATOR_BY_KEY)
_LIST_SPECS = tuple(spec for spec in SEARCH_OPERATOR_SPECS if spec.value_kind == "list")
_GROUP_SPECS = tuple(spec for spec in SEARCH_OPERATOR_SPECS if spec.value_kind == "groups")
_SPACE_RE = re.compile(r"\s+")
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
    re.IGNORECASE,
)
_FILETYPE_RE = re.compile(r"^[a-z0-9]{1,12}$", re.IGNORECASE)

class PlanValidationError(ValueError):
    """One or more structural problems in an advanced search plan."""

    def __init__(self, issues: list[dict[str, str]]):
        self.issues = issues
        super().__init__("INVALID_SEARCH_PLAN")


def _clean_text(value: Any) -> str:
    return _SPACE_RE.sub(" ", str(value or "").replace("\r", " ").replace("\n", " ")).strip()


def _string_schema(description: str, *, max_length: int) -> dict[str, Any]:
    return {
        "type": "string",
        "minLength": 1,
        "maxLength": max_length,
        "description": description,
    }


def _list_schema(description: str, *, max_items: int, max_length: int) -> dict[str, Any]:
    return {
        "type": "array",
        "maxItems": max_items,
        "items": _string_schema(description, max_length=max_length),
    }


def build_advanced_search_schema(*, tor_enabled: bool = False) -> dict[str, Any]:
    verticals = [*_BASE_VERTICALS, *(("onion",) if tor_enabled else ())]
    operator_properties: dict[str, Any] = {}
    for spec in SEARCH_OPERATOR_SPECS:
        if spec.value_kind == "list":
            operator_properties[spec.key] = _list_schema(
                spec.description,
                max_items=spec.max_items,
                max_length=spec.max_length,
            )
        elif spec.value_kind == "groups":
            operator_properties[spec.key] = {
                "type": "array",
                "maxItems": spec.max_items,
                "items": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": spec.group_max_items,
                    "items": _string_schema(spec.description, max_length=spec.max_length),
                },
                "description": spec.description,
            }
        else:
            operator_properties[spec.key] = {
                "type": "string",
                "format": "date",
                "description": spec.description,
            }
    operators = {
        "type": "object",
        "additionalProperties": False,
        "properties": operator_properties,
    }
    query_item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "vertical": {
                "type": "string",
                "enum": verticals,
                "description": (
                    "Required routing from the research plan. MUST use shopping for product "
                    "discovery, budgets, prices, sellers, stock, or availability; MUST use "
                    "academic for papers, citations, DOI records, preprints, peer-reviewed "
                    "support, or primary scientific literature; use web for official, "
                    "independent, community, reporting, measurement, and general evidence."
                ),
            },
            "text": _string_schema(
                "Core search terms only. Never include a four-digit calendar year; encode "
                "a necessary time boundary exclusively in operators.after or operators.before.",
                max_length=ADVANCED_TEXT_LIMIT,
            ),
            "operators": operators,
        },
        "required": ["vertical", "text"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "description": _string_schema(
                "Visible activity title for the current research step, not a query. Write "
                "a natural 3-4 word phrase in the user's language, beginning with an action "
                "verb and naming the evidence goal; it must make sense without the query text.",
                max_length=DESCRIPTION_LIMIT,
            ),
            "queries": {
                "type": "array",
                "minItems": 1,
                "maxItems": ADVANCED_BATCH_LIMIT,
                "items": query_item,
                "description": (
                    "Normally one query. Each additional item represents an independently "
                    "necessary deliverable with its own evidence set or vertical."
                ),
            },
            "effort": {
                "type": "string",
                "enum": list(_EFFORTS),
                "default": "medium",
                "description": "Shared search effort. Start with medium; high is a gated reserve tier.",
            },
        },
        "required": ["description", "queries"],
    }


def _issue(issues: list[dict[str, str]], path: str, message: str) -> None:
    issues.append({"path": path, "message": message})


def _normalize_domain(value: str) -> str:
    raw = _clean_text(value).lower()
    if "://" in raw:
        parsed = urlsplit(raw)
        raw = parsed.hostname or ""
    else:
        raw = raw.split("/", 1)[0].split(":", 1)[0]
    raw = raw.removeprefix("www.").rstrip(".")
    try:
        raw = raw.encode("idna").decode("ascii")
    except UnicodeError:
        return ""
    return raw if _DOMAIN_RE.fullmatch(raw) else ""


def _normalize_list(
    operators: dict[str, Any], spec: SearchOperatorSpec, path: str,
    issues: list[dict[str, str]],
) -> list[str]:
    value = operators.get(spec.key, [])
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        _issue(issues, path, "must be an array")
        return []
    if len(value) > spec.max_items:
        _issue(issues, path, f"must contain at most {spec.max_items} items")
    output: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value[:spec.max_items]):
        item_path = f"{path}[{index}]"
        if not isinstance(item, str):
            _issue(issues, item_path, "must be a string")
            continue
        text = _clean_text(item)
        if not text:
            _issue(issues, item_path, "must not be empty")
            continue
        if len(text) > spec.max_length:
            _issue(issues, item_path, f"must be at most {spec.max_length} characters")
            continue
        if spec.normalizer == "domain":
            text = _normalize_domain(text)
            if not text:
                _issue(issues, item_path, "must be a fully qualified domain")
                continue
        elif spec.normalizer == "file_type":
            text = text.lower().lstrip(".")
            if not _FILETYPE_RE.fullmatch(text):
                _issue(issues, item_path, "must be a file extension containing only letters or digits")
                continue
        marker = text.casefold()
        if marker not in seen:
            seen.add(marker)
            output.append(text)
    return output


def _normalize_date(value: Any, path: str, issues: list[dict[str, str]]) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        _issue(issues, path, "must be an ISO date string")
        return ""
    text = value.strip()
    try:
        parsed = dt.date.fromisoformat(text)
    except ValueError:
        _issue(issues, path, "must use YYYY-MM-DD")
        return ""
    return parsed.isoformat()


def _normalize_groups(
    operators: dict[str, Any], spec: SearchOperatorSpec, path: str,
    issues: list[dict[str, str]],
) -> list[list[str]]:
    value = operators.get(spec.key, [])
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        _issue(issues, path, "must be an array of arrays")
        return []
    if len(value) > spec.max_items:
        _issue(issues, path, f"must contain at most {spec.max_items} groups")
    output: list[list[str]] = []
    seen_groups: set[tuple[str, ...]] = set()
    for group_index, raw_group in enumerate(value[:spec.max_items]):
        group_path = f"{path}[{group_index}]"
        if not isinstance(raw_group, list):
            _issue(issues, group_path, "must be an array")
            continue
        if len(raw_group) < 2:
            _issue(issues, group_path, "must contain at least two alternatives")
        if len(raw_group) > spec.group_max_items:
            _issue(
                issues,
                group_path,
                f"must contain at most {spec.group_max_items} alternatives",
            )
        group: list[str] = []
        seen: set[str] = set()
        for item_index, item in enumerate(raw_group[:spec.group_max_items]):
            item_path = f"{group_path}[{item_index}]"
            if not isinstance(item, str):
                _issue(issues, item_path, "must be a string")
                continue
            text = _clean_text(item)
            if not text:
                _issue(issues, item_path, "must not be empty")
                continue
            if len(text) > spec.max_length:
                _issue(issues, item_path, f"must be at most {spec.max_length} characters")
                continue
            marker = text.casefold()
            if marker not in seen:
                seen.add(marker)
                group.append(text)
        if len(group) < 2:
            _issue(issues, group_path, "must contain two distinct alternatives")
            continue
        group_marker = tuple(item.casefold() for item in group)
        if group_marker not in seen_groups:
            seen_groups.add(group_marker)
            output.append(group)
    return output


def _quoted(value: str) -> str:
    return f'"{_clean_text(value).replace(chr(34), "")}"'


def _operator_value(value: str) -> str:
    clean = _clean_text(value).replace('"', "")
    return _quoted(clean) if " " in clean else clean


def _or_group(values: list[str], render) -> str:
    rendered = [render(value) for value in values]
    if not rendered:
        return ""
    return rendered[0] if len(rendered) == 1 else f"({' OR '.join(rendered)})"


def _compile_operator(spec: SearchOperatorSpec, value: Any) -> str | list[str]:
    if spec.value_kind == "date":
        return f"{spec.prefix}{value}" if value else ""
    values = list(value or [])
    if spec.compile_kind == "quoted":
        return [_quoted(item) for item in values]
    if spec.compile_kind == "or":
        return _or_group(values, _operator_value)
    if spec.compile_kind == "or_groups":
        return [_or_group(group, _operator_value) for group in values]
    if spec.compile_kind == "exclude":
        return [f"{spec.prefix}{_operator_value(item)}" for item in values]
    if spec.compile_kind == "or_prefix":
        return _or_group(values, lambda item: f"{spec.prefix}{item}")
    if spec.compile_kind == "prefix":
        return [f"{spec.prefix}{_operator_value(item)}" for item in values]
    return ""


def _compile_query(text: str, operators: dict[str, Any], qcfg: object) -> tuple[str, str | None]:
    clean_text, timelimit = resolve_query_dates(text, qcfg)
    parts = [clean_text]
    for spec in SEARCH_OPERATOR_SPECS:
        compiled = _compile_operator(spec, operators.get(spec.key))
        if isinstance(compiled, list):
            parts.extend(compiled)
        elif compiled:
            parts.append(compiled)
    return " ".join(part for part in parts if part), timelimit


def prepare_advanced_search(
    arguments: Any, *, query_config: object, tor_enabled: bool = False
) -> dict[str, Any]:
    """Validate and normalize one advanced plan, or raise PlanValidationError."""

    issues: list[dict[str, str]] = []
    if not isinstance(arguments, dict):
        raise PlanValidationError([{"path": "$", "message": "must be an object"}])
    unknown_root = sorted(set(arguments) - {"description", "queries", "effort"})
    for key in unknown_root:
        _issue(issues, f"$.{key}", "is not allowed in advanced mode")

    raw_description = arguments.get("description")
    if not isinstance(raw_description, str):
        _issue(issues, "$.description", "must be a string")
    description = _clean_text(raw_description) if isinstance(raw_description, str) else ""
    if not description:
        _issue(issues, "$.description", "must be a non-empty string")
    elif len(description) > DESCRIPTION_LIMIT:
        _issue(issues, "$.description", f"must be at most {DESCRIPTION_LIMIT} characters")

    effort_value = arguments.get("effort", "medium")
    if not isinstance(effort_value, str):
        _issue(issues, "$.effort", "must be a string")
    effort = str(effort_value or "").strip().lower()
    if effort not in _EFFORTS:
        _issue(issues, "$.effort", "must be one of low, medium, high")
        effort = "medium"

    raw_queries = arguments.get("queries")
    if not isinstance(raw_queries, list):
        _issue(issues, "$.queries", "must be an array")
        raw_queries = []
    elif not raw_queries:
        _issue(issues, "$.queries", "must contain at least one item")
    elif len(raw_queries) > ADVANCED_BATCH_LIMIT:
        _issue(issues, "$.queries", f"must contain at most {ADVANCED_BATCH_LIMIT} items")

    allowed_verticals = {*_BASE_VERTICALS, *({"onion"} if tor_enabled else set())}
    canonical_queries: list[dict[str, Any]] = []
    prepared_queries: list[dict[str, Any]] = []
    for index, raw_query in enumerate(raw_queries[:ADVANCED_BATCH_LIMIT]):
        base_path = f"$.queries[{index}]"
        if not isinstance(raw_query, dict):
            _issue(issues, base_path, "must be an object")
            continue
        for key in sorted(set(raw_query) - {"vertical", "text", "operators"}):
            _issue(issues, f"{base_path}.{key}", "is not allowed")

        raw_text = raw_query.get("text")
        raw_vertical = raw_query.get("vertical")
        if not isinstance(raw_text, str):
            _issue(issues, f"{base_path}.text", "must be a string")
        if not isinstance(raw_vertical, str):
            _issue(issues, f"{base_path}.vertical", "must be a string")
        text = _clean_text(raw_text) if isinstance(raw_text, str) else ""
        vertical = raw_vertical.strip().lower() if isinstance(raw_vertical, str) else ""
        if not text:
            _issue(issues, f"{base_path}.text", "must be a non-empty string")
        elif len(text) > ADVANCED_TEXT_LIMIT:
            _issue(issues, f"{base_path}.text", f"must be at most {ADVANCED_TEXT_LIMIT} characters")
        elif has_search_operators(text):
            _issue(issues, f"{base_path}.text", "must not contain recognized search operators")
        if vertical not in allowed_verticals:
            allowed = ", ".join(sorted(allowed_verticals))
            _issue(issues, f"{base_path}.vertical", f"must be one of {allowed}")

        raw_operators = raw_query.get("operators", {})
        if raw_operators in (None, ""):
            raw_operators = {}
        if not isinstance(raw_operators, dict):
            _issue(issues, f"{base_path}.operators", "must be an object")
            raw_operators = {}
        for key in sorted(set(raw_operators) - set(_OPERATOR_KEYS)):
            _issue(issues, f"{base_path}.operators.{key}", "is not a supported operator")

        normalized_operators: dict[str, Any] = {}
        for spec in _LIST_SPECS:
            values = _normalize_list(
                raw_operators, spec, f"{base_path}.operators.{spec.key}", issues
            )
            if values:
                normalized_operators[spec.key] = values
        for spec in _GROUP_SPECS:
            groups = _normalize_groups(
                raw_operators, spec, f"{base_path}.operators.{spec.key}", issues
            )
            if groups:
                normalized_operators[spec.key] = groups
        after = _normalize_date(raw_operators.get("after"), f"{base_path}.operators.after", issues)
        before = _normalize_date(raw_operators.get("before"), f"{base_path}.operators.before", issues)
        if after:
            normalized_operators["after"] = after
        if before:
            normalized_operators["before"] = before
        if after and before and after >= before:
            _issue(issues, f"{base_path}.operators", "after must be earlier than before")

        compiled_query, timelimit = _compile_query(text, normalized_operators, query_config)
        if len(compiled_query) > COMPILED_QUERY_LIMIT:
            _issue(
                issues,
                base_path,
                f"compiled query must be at most {COMPILED_QUERY_LIMIT} characters",
            )

        canonical_item: dict[str, Any] = {
            "vertical": vertical,
            "text": text,
        }
        if normalized_operators:
            canonical_item["operators"] = normalized_operators
        canonical_queries.append(canonical_item)
        prepared_queries.append(
            {
                **canonical_item,
                "operators": normalized_operators,
                "compiled_query": compiled_query,
                "timelimit": timelimit,
            }
        )

    if issues:
        raise PlanValidationError(issues)
    return {
        "canonical_arguments": {
            "description": description,
            "queries": canonical_queries,
            "effort": effort,
        },
        "search_request": {
            "schema_mode": "advanced",
            "description": description,
            "effort": effort,
            "queries": prepared_queries,
        },
    }
