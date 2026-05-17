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
    preview_model_warm_timeout: float = 10.0
    preview_curl_timeout: float = 12.0
    pdf_preview_fetch_timeout: float = 20.0
    pdf_preview_extract_timeout: float = 15.0
    prefetch_fetch_timeout: float = 8.0
    max_snippet_chars: int = 2_000
    preview_min_chars: int = 600
    preview_max_chars: int = 4_000
    total_context_budget: int = 40_000  # max chars in total search output (0 = no limit)
    early_return_threshold: int = 0     # cancel remaining fetches after N good previews (0 = disabled)
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


_DEFAULT_FILLER_LOW_EFFORT_TERMS: tuple[str, ...] = (
    "authoritative",
    "all the requirements",
    "best",
    "complete",
    "comprehensive",
    "critical",
    "definitive",
    "essential",
    "exhaustive",
    "expert",
    "flawless",
    "full",
    "ideal",
    "important",
    "in-depth",
    "optimal",
    "perfect",
    "premier",
    "superior",
    "thorough",
    "ultimate",
    "unrivaled",
    "advanced",
    "breakthrough",
    "effortless",
    "elite",
    "exceptional",
    "exclusive",
    "extraordinary",
    "game-changing",
    "groundbreaking",
    "leading",
    "notable",
    "powerful",
    "proven",
    "remarkable",
    "reliable",
    "robust",
    "seamless",
    "top-tier",
    "world-class",
    "beste",
    "bester",
    "bestes",
    "besten",
    "vollständig",
    "vollständige",
    "vollständiger",
    "ultimativ",
    "ultimative",
    "wichtig",
    "wichtige",
    "wichtigste",
    "meilleur",
    "meilleure",
    "meilleurs",
    "meilleures",
    "complet",
    "complète",
    "complets",
    "complètes",
    "ultime",
    "important",
    "importante",
    "mejor",
    "mejores",
    "completo",
    "completa",
    "completos",
    "completas",
    "definitivo",
    "definitiva",
    "perfecto",
    "perfecta",
    "perfectos",
    "perfectas",
    "importante",
    "importantes",
    "melhor",
    "melhores",
    "completo",
    "completa",
    "definitivo",
    "definitiva",
    "migliore",
    "migliori",
    "completo",
    "completa",
    "definitivo",
    "definitiva",
    "bästa",
    "bäst",
    "komplett",
    "viktig",
    "viktigaste",
    "bedste",
    "komplet",
    "vigtig",
    "vigtigste",
    "paras",
    "parhaat",
    "täydellinen",
    "tärkeä",
    "tärkein",
    "najlepszy",
    "najlepsza",
    "najlepsze",
    "kompletny",
    "kompletna",
    "ważny",
    "ważna",
    "nejlepší",
    "kompletní",
    "důležitý",
    "důležitá",
    "najlepší",
    "kompletný",
    "dôležitý",
    "dôležitá",
    "legjobb",
    "teljes",
    "fontos",
    "en iyi",
    "mükemmel",
    "kusursuz",
    "tam",
    "önemli",
    "أفضل",
    "الأفضل",
    "مثالي",
    "كامل",
    "شامل",
    "مهم",
    "הטוב ביותר",
    "מושלם",
    "מלא",
    "חשוב",
    "بهترین",
    "کامل",
    "مهم",
    "بهترین",
    "مکمل",
    "اہم",
    "最佳",
    "最好",
    "完美",
    "完整",
    "全面",
    "重要",
    "ベスト",
    "最高",
    "完璧",
    "完全",
    "重要",
    "최고",
    "완벽한",
    "완전한",
    "중요한",
    "सबसे अच्छा",
    "बेहतरीन",
    "पूर्ण",
    "महत्वपूर्ण",
    "সেরা",
    "সম্পূর্ণ",
    "গুরুত্বপূর্ণ",
    "terbaik",
    "sempurna",
    "lengkap",
    "penting",
    "tốt nhất",
    "hoàn hảo",
    "đầy đủ",
    "quan trọng",
    "ดีที่สุด",
    "สมบูรณ์แบบ",
    "ครบถ้วน",
    "สำคัญ",
    "безупречная",
    "безупречное",
    "безупречные",
    "безупречный",
    "идеальная",
    "идеальное",
    "идеальные",
    "идеальный",
    "исчерпывающая",
    "исчерпывающее",
    "исчерпывающие",
    "исчерпывающий",
    "критически важная",
    "критически важное",
    "критически важный",
    "критически важные",
    "лучшая",
    "лучшее",
    "лучшие",
    "лучший",
    "оптимальная",
    "оптимальное",
    "оптимальные",
    "оптимальный",
    "полная",
    "полное",
    "полные",
    "полный",
)


_DEFAULT_FILLER_LOW_EFFORT_EXEMPT_PHRASES: tuple[str, ...] = (
    "critical section",
    "critical path",
    "exhaustive search",
    "full text search",
    "optimal transport",
)


@dataclass
class QueryQualitySection:
    """Controls optional soft handling of title-like/filler wording.

    This is separate from the hard BAD_QUERY gate.  It is disabled by default
    because filler-like adjectives can be valid technical terms in context.
    """

    filler_low_effort_enabled: bool = False
    filler_low_effort_min_hits: int = 1
    filler_low_effort_target: str = "low"
    filler_low_effort_notice: bool = True
    filler_low_effort_terms: tuple[str, ...] = field(
        default_factory=lambda: _DEFAULT_FILLER_LOW_EFFORT_TERMS
    )
    filler_low_effort_exempt_phrases: tuple[str, ...] = field(
        default_factory=lambda: _DEFAULT_FILLER_LOW_EFFORT_EXEMPT_PHRASES
    )


@dataclass
class EffortSection:
    low_hard_timeout: float = 9.0
    medium_hard_timeout: float = 20.0
    high_hard_timeout: float = 60.0
    low_max_results: int = 5
    high_multiplier: int = 3
    low_total_context_budget: int = 6_000
    low_candidate_pool_multiplier: int = 1
    low_ddgs_hedge_count: int = 1
    low_ddgs_worker_timeout: float = 8.0
    medium_ddgs_worker_timeout: float = 10.0
    high_ddgs_worker_timeout: float = 18.0
    low_ddgs_engine_timeout: int = 5
    low_ddgs_max_retries: int = 1
    low_preview_fetch_timeout: float = 2.0
    low_preview_total_timeout: float = 4.0
    medium_preview_fetch_timeout: float = 6.0
    medium_preview_total_timeout: float = 12.0
    high_preview_fetch_timeout: float = 18.0
    high_preview_total_timeout: float = 36.0
    zero_result_fallback_max_results: int = 10
    zero_result_fallback_candidate_pool_multiplier: int = 1
    zero_result_fallback_ddgs_worker_timeout: float = 8.0
    zero_result_fallback_ddgs_engine_timeout: int = 5
    zero_result_fallback_ddgs_max_retries: int = 1
    timeout_fallback_min_window: float = 3.0
    timeout_fallback_max_window: float = 8.0
    timeout_fallback_fraction: float = 0.4


@dataclass
class SearchConfig:
    search: SearchSection = field(default_factory=SearchSection)
    extraction: ExtractionSection = field(default_factory=ExtractionSection)
    cache: CacheSection = field(default_factory=CacheSection)
    query: QuerySection = field(default_factory=QuerySection)
    query_quality: QueryQualitySection = field(default_factory=QueryQualitySection)
    effort: "EffortSection" = field(default_factory=lambda: EffortSection())


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


def _string_tuple(value: object, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is _MISSING:
        return default
    if not isinstance(value, list):
        return default
    return tuple(str(item).strip().lower() for item in value if str(item).strip())


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
    qq = raw.get("query_quality", {})
    effort = raw.get("effort", {})

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
            candidate_pool_multiplier=int(s.get("candidate_pool_multiplier", 2)),
            auto_scrape_preview=bool(s.get("auto_scrape_preview", True)),
            preview_fetch_limit=int(s.get("preview_fetch_limit", 10)),
            preview_fetch_timeout=float(s.get("preview_fetch_timeout", 4.0)),
            preview_total_timeout=float(s.get("preview_total_timeout", 10.0)),
            preview_model_warm_timeout=float(s.get("preview_model_warm_timeout", 10.0)),
            preview_curl_timeout=float(s.get("preview_curl_timeout", 12.0)),
            pdf_preview_fetch_timeout=float(s.get("pdf_preview_fetch_timeout", 20.0)),
            pdf_preview_extract_timeout=float(s.get("pdf_preview_extract_timeout", 15.0)),
            prefetch_fetch_timeout=float(s.get("prefetch_fetch_timeout", 8.0)),
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
        query_quality=QueryQualitySection(
            filler_low_effort_enabled=bool(qq.get("filler_low_effort_enabled", False)),
            filler_low_effort_min_hits=max(1, int(qq.get("filler_low_effort_min_hits", 1))),
            filler_low_effort_target=str(qq.get("filler_low_effort_target", "low")),
            filler_low_effort_notice=bool(qq.get("filler_low_effort_notice", True)),
            filler_low_effort_terms=_string_tuple(
                qq.get("filler_low_effort_terms", _MISSING),
                _DEFAULT_FILLER_LOW_EFFORT_TERMS,
            ),
            filler_low_effort_exempt_phrases=_string_tuple(
                qq.get("filler_low_effort_exempt_phrases", _MISSING),
                _DEFAULT_FILLER_LOW_EFFORT_EXEMPT_PHRASES,
            ),
        ),
        effort=EffortSection(
            low_hard_timeout=float(effort.get("low_hard_timeout", 9.0)),
            medium_hard_timeout=float(effort.get("medium_hard_timeout", 20.0)),
            high_hard_timeout=float(effort.get("high_hard_timeout", 60.0)),
            low_max_results=int(effort.get("low_max_results", 5)),
            high_multiplier=int(effort.get("high_multiplier", 3)),
            low_total_context_budget=int(effort.get("low_total_context_budget", 6_000)),
            low_candidate_pool_multiplier=int(effort.get("low_candidate_pool_multiplier", 1)),
            low_ddgs_hedge_count=int(effort.get("low_ddgs_hedge_count", 1)),
            low_ddgs_worker_timeout=float(effort.get("low_ddgs_worker_timeout", 8.0)),
            medium_ddgs_worker_timeout=float(effort.get("medium_ddgs_worker_timeout", 10.0)),
            high_ddgs_worker_timeout=float(effort.get("high_ddgs_worker_timeout", 18.0)),
            low_ddgs_engine_timeout=int(effort.get("low_ddgs_engine_timeout", 5)),
            low_ddgs_max_retries=int(effort.get("low_ddgs_max_retries", 1)),
            low_preview_fetch_timeout=float(effort.get("low_preview_fetch_timeout", 2.0)),
            low_preview_total_timeout=float(effort.get("low_preview_total_timeout", 4.0)),
            medium_preview_fetch_timeout=float(effort.get("medium_preview_fetch_timeout", 6.0)),
            medium_preview_total_timeout=float(effort.get("medium_preview_total_timeout", 12.0)),
            high_preview_fetch_timeout=float(effort.get("high_preview_fetch_timeout", 18.0)),
            high_preview_total_timeout=float(effort.get("high_preview_total_timeout", 36.0)),
            zero_result_fallback_max_results=int(effort.get("zero_result_fallback_max_results", 10)),
            zero_result_fallback_candidate_pool_multiplier=int(
                effort.get("zero_result_fallback_candidate_pool_multiplier", 1)
            ),
            zero_result_fallback_ddgs_worker_timeout=float(
                effort.get("zero_result_fallback_ddgs_worker_timeout", 8.0)
            ),
            zero_result_fallback_ddgs_engine_timeout=int(
                effort.get("zero_result_fallback_ddgs_engine_timeout", 5)
            ),
            zero_result_fallback_ddgs_max_retries=int(
                effort.get("zero_result_fallback_ddgs_max_retries", 1)
            ),
            timeout_fallback_min_window=float(effort.get("timeout_fallback_min_window", 3.0)),
            timeout_fallback_max_window=float(effort.get("timeout_fallback_max_window", 8.0)),
            timeout_fallback_fraction=float(effort.get("timeout_fallback_fraction", 0.4)),
        ),
    )

    if path is None:
        _cached_config = config
    return config
