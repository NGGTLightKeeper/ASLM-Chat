# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Search configuration loader.

Reads search_config.json from this directory and exposes a typed
SearchConfig dataclass. All service-layer modules import from here;
no module should read JSON directly.

Public API
----------
SearchConfig      -- typed configuration dataclass
load_search_config() -> SearchConfig
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("config.search")

_CONFIG_PATH = Path(__file__).parent / "search_config.json"


# ---------------------------------------------------------------------------
# Typed config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SearchSection:
    timeout_seconds: float = 40.0
    ddgs_engine_timeout: int = 8   # per-HTTP-request timeout for each search engine call
    tls_verify: bool = True        # set False only behind corporate MITM proxies
    max_results: int = 10
    result_buffer_size: int = 0   # extra results fetched; final output stays max_results
    batch_query_limit: int = 10
    candidate_pool_multiplier: int = 2
    auto_scrape_preview: bool = True
    preview_fetch_limit: int = 10
    preview_fetch_timeout: float = 4.0   # per-URL fetch timeout (seconds)
    preview_total_timeout: float = 10.0  # per-URL race total timeout (seconds)
    max_snippet_chars: int = 2_000
    preview_min_chars: int = 600
    preview_max_chars: int = 4_000
    total_context_budget: int = 40_000  # max chars in total search output (0 = no limit)
    early_return_threshold: int = 0     # cancel remaining fetches after N good previews (0 = disabled)
    bot_mimic_mode: str = "off"         # off | fallback | always
    bot_mimic_top_k: int = 6
    bot_mimic_timeout_seconds: float = 0.8
    bot_mimic_for_query_types: list[str] = field(default_factory=list)
    bot_mimic_only_for_rank_enrichment: bool = True
    enable_gliner: bool = False
    gliner_trigger_min_score: float = 0.18


@dataclass
class ExtractionSection:
    timeout_seconds: float = 25.0
    max_page_chars: int = 20_000
    min_content_length: int = 800


@dataclass
class CacheSection:
    search_ttl_seconds: int = 1_800
    page_ttl_seconds: int = 86_400


@dataclass
class QuerySection:
    """Controls how year tokens in search queries are interpreted.

    year_hint_mode:
        "timelimit" — extract the year, derive a timelimit from it, then
                      strip it from the query so the search engine doesn't
                      treat it as a keyword.  Most useful behavior.
        "strip"     — strip years when freshness hints are present, but do
                      not use them to set a timelimit (legacy behavior).
        "none"      — leave years in the query untouched.

    year_hint_current / year_hint_prev / year_hint_older:
        DDGS timelimit ("d"/"w"/"m"/"y") or null (no restriction) applied
        when the extracted year equals the current year, the previous year,
        or anything older.  Null means "no additional restriction".
    """
    year_hint_mode: str = "timelimit"
    year_hint_current: Optional[str] = "m"  # year == this year  → last month
    year_hint_prev: Optional[str] = "y"     # year == last year  → last year
    year_hint_older: Optional[str] = None  # year < last year  → no restriction


@dataclass
class SearchConfig:
    search: SearchSection = field(default_factory=SearchSection)
    extraction: ExtractionSection = field(default_factory=ExtractionSection)
    cache: CacheSection = field(default_factory=CacheSection)
    query: QuerySection = field(default_factory=QuerySection)


# ---------------------------------------------------------------------------
# Loader (singleton pattern)
# ---------------------------------------------------------------------------

_cached_config: SearchConfig | None = None

_MISSING = object()


def _optional_string(value: object, default: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if value == "":
        return None
    if value is _MISSING:
        return default
    return str(value)


def load_search_config(path: Path | None = None) -> SearchConfig:
    """Load and return the SearchConfig singleton.

    Subsequent calls return the cached instance.
    Pass a custom *path* only in tests.
    """
    global _cached_config
    if _cached_config is not None and path is None:
        return _cached_config

    target = path or _CONFIG_PATH
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("search_config.json not found at %s — using defaults", target)
        _cached_config = SearchConfig()
        return _cached_config
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in %s: %s — using defaults", target, exc)
        _cached_config = SearchConfig()
        return _cached_config

    s = raw.get("search", {})
    e = raw.get("extraction", {})
    c = raw.get("cache", {})
    q = raw.get("query", {})

    config = SearchConfig(
        search=SearchSection(
            timeout_seconds=float(s.get("timeout_seconds", 40.0)),
            ddgs_engine_timeout=int(s.get("ddgs_engine_timeout", 8)),
            tls_verify=bool(s.get("tls_verify", True)),
            max_results=int(s.get("max_results", 10)),
            result_buffer_size=int(s.get("result_buffer_size", 0)),
            batch_query_limit=int(s.get("batch_query_limit", 10)),
            total_context_budget=int(s.get("total_context_budget", 40_000)),
            early_return_threshold=int(s.get("early_return_threshold", 0)),
            bot_mimic_mode=str(s.get("bot_mimic_mode", "off")).strip().lower() or "off",
            bot_mimic_top_k=max(0, int(s.get("bot_mimic_top_k", 6))),
            bot_mimic_timeout_seconds=max(0.1, float(s.get("bot_mimic_timeout_seconds", 0.8))),
            bot_mimic_for_query_types=[
                str(item).strip().lower()
                for item in (s.get("bot_mimic_for_query_types") or [])
                if str(item).strip()
            ],
            bot_mimic_only_for_rank_enrichment=bool(s.get("bot_mimic_only_for_rank_enrichment", True)),
            candidate_pool_multiplier=int(s.get("candidate_pool_multiplier", 2)),
            auto_scrape_preview=bool(s.get("auto_scrape_preview", True)),
            preview_fetch_limit=int(s.get("preview_fetch_limit", 10)),
            preview_fetch_timeout=float(s.get("preview_fetch_timeout", 4.0)),
            preview_total_timeout=float(s.get("preview_total_timeout", 10.0)),
            max_snippet_chars=int(s.get("max_snippet_chars", raw.get("max_snippet_chars", 2_000))),
            preview_min_chars=int(s.get("preview_min_chars", 600)),
            preview_max_chars=int(s.get("preview_max_chars", 4_000)),
            enable_gliner=bool(s.get("enable_gliner", False)),
            gliner_trigger_min_score=float(s.get("gliner_trigger_min_score", 0.18)),
        ),
        extraction=ExtractionSection(
            timeout_seconds=float(e.get("timeout_seconds", 25.0)),
            max_page_chars=int(e.get("max_page_chars", 20_000)),
            min_content_length=int(e.get("min_content_length", 800)),
        ),
        cache=CacheSection(
            search_ttl_seconds=int(c.get("search_ttl_seconds", 1_800)),
            page_ttl_seconds=int(c.get("page_ttl_seconds", 86_400)),
        ),
        query=QuerySection(
            year_hint_mode=str(q.get("year_hint_mode", "timelimit")),
            year_hint_current=_optional_string(q.get("year_hint_current", _MISSING), "m"),
            year_hint_prev=_optional_string(q.get("year_hint_prev", _MISSING), "y"),
            year_hint_older=_optional_string(q.get("year_hint_older", _MISSING), None),
        ),
    )

    if path is None:
        _cached_config = config
    return config
