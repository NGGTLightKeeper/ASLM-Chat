# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


_SITE_TOKEN_RE = re.compile(r"(?<!\S)(-?)site:([a-z0-9.-]+\.[a-z]{2,})(?=\s|$)", re.IGNORECASE)
_BARE_EXCLUDE_RE = re.compile(r"(?<!\S)-([a-z0-9.-]+\.[a-z]{2,})(?=\s|$)", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")


# Parsed site: include/exclude domain operators from a search query.
@dataclass(slots=True)
class DomainConstraints:
    include_domains: list[str] = field(default_factory=list)
    exclude_domains: list[str] = field(default_factory=list)
    clean_query: str = ""
    raw_tokens: list[str] = field(default_factory=list)

    # True when include or exclude site: constraints are present.
    @property
    def has_constraints(self) -> bool:
        return bool(self.include_domains or self.exclude_domains)


# Lowercase host pattern, strip www. and trailing dot.
def _normalize_domain(domain: str) -> str:
    value = (domain or "").strip().lower().rstrip(".")
    if value.startswith("www."):
        value = value[4:]
    return value


# Match exact host or subdomain of pattern.
def _is_host_match(host: str, pattern: str) -> bool:
    host = _normalize_domain(host)
    pattern = _normalize_domain(pattern)
    return bool(host and pattern and (host == pattern or host.endswith(f".{pattern}")))


# Append value to list if not already present.
def _append_unique(target: list[str], value: str) -> None:
    if value and value not in target:
        target.append(value)


# Remove leading/trailing OR connectors left after site: token removal.
def _strip_orphan_domain_connectors(text: str) -> str:
    tokens = (text or "").split()
    while tokens and tokens[0].lower() in {"or", "|"}:
        tokens.pop(0)
    while tokens and tokens[-1].lower() in {"or", "|"}:
        tokens.pop()
    return " ".join(tokens)


# Parse site: and bare -domain tokens from a search query string.
def parse_domain_constraints(query: str) -> DomainConstraints:
    text = query or ""
    include_domains: list[str] = []
    exclude_domains: list[str] = []
    raw_tokens: list[str] = []

    # Regex replacer for site: and -site: tokens.
    def _site_replace(match: re.Match[str]) -> str:
        negated = match.group(1) == "-"
        domain = _normalize_domain(match.group(2))
        raw_tokens.append(match.group(0))
        if negated:
            _append_unique(exclude_domains, domain)
        else:
            _append_unique(include_domains, domain)
        return " "

    cleaned = _SITE_TOKEN_RE.sub(_site_replace, text)
    if raw_tokens:
        cleaned = _strip_orphan_domain_connectors(cleaned)

    # Regex replacer for bare -domain exclude tokens.
    def _bare_replace(match: re.Match[str]) -> str:
        domain = _normalize_domain(match.group(1))
        raw = match.group(0)
        if domain in include_domains or domain in exclude_domains:
            return raw
        raw_tokens.append(raw)
        _append_unique(exclude_domains, domain)
        return " "

    cleaned = _BARE_EXCLUDE_RE.sub(_bare_replace, cleaned)
    cleaned = _SPACE_RE.sub(" ", cleaned).strip()

    return DomainConstraints(
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        clean_query=cleaned,
        raw_tokens=raw_tokens,
    )


# Rebuild provider query with site: operators from parsed constraints.
def build_provider_query(raw_query: str, constraints: DomainConstraints) -> str:
    clean = constraints.clean_query or (raw_query or "").strip()
    if not constraints.has_constraints:
        return clean

    parts: list[str] = []
    if constraints.include_domains:
        include_expr = " OR ".join(f"site:{domain}" for domain in constraints.include_domains)
        parts.append(include_expr)
        if clean:
            parts.append(clean)
        parts.extend(f"-site:{domain}" for domain in constraints.exclude_domains)
        return " ".join(parts).strip()

    parts.append(clean)
    parts.extend(f"-site:{domain}" for domain in constraints.exclude_domains)
    return " ".join(part for part in parts if part).strip()


# Check whether a URL host satisfies include/exclude domain constraints.
def matches_domain_constraints(url: str, constraints: DomainConstraints) -> bool:
    if not constraints.has_constraints:
        return True

    host = _normalize_domain(urlparse(url).netloc)
    if not host:
        return False

    if any(_is_host_match(host, domain) for domain in constraints.exclude_domains):
        return False

    if constraints.include_domains:
        return any(_is_host_match(host, domain) for domain in constraints.include_domains)

    return True


# Filter result objects whose url attribute fails domain constraints.
def filter_results_by_domain_constraints(
    results: list[Any],
    constraints: DomainConstraints,
) -> list[Any]:
    if not constraints.has_constraints:
        return results
    return [
        result
        for result in results
        if matches_domain_constraints(getattr(result, "url", ""), constraints)
    ]
