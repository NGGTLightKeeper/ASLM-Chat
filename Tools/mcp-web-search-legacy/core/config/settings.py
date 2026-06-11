# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.config.pipeline_modes import normalize_pipeline_mode

logger = logging.getLogger("config.search")

_CONFIG_PATH = Path(__file__).parent / "search_config.json"


# Typed config dataclasses (loaded from search_config.json).
@dataclass
class SearchSection:
    timeout_seconds: float = 40.0
    ddgs_engine_timeout: int = 8   # per-HTTP-request timeout for each search engine call
    tls_verify: bool = True        # set False only behind corporate MITM proxies
    max_results: int = 10
    result_buffer_size: int = 0   # extra results fetched; final output stays max_results
    batch_query_limit: int = 10
    candidate_pool_multiplier: int = 2
    routing_profile: str = "stability"
    stability_ddgs_attempts: int = 2
    quality_ddgs_attempts: int = 4
    quality_ddgs_worker_timeout: float = 26.0
    quality_hard_timeout: float = 40.0
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
    enable_read_page_compress: bool = True
    read_page_compress_threshold_chars: int = 10_000
    read_page_compress_target_chars: int = 10_000


@dataclass
class CacheSection:
    search_ttl_seconds: int = 1_800
    page_ttl_seconds: int = 86_400


# Year tokens in queries: timelimit (default), strip, or none — see year_hint_* fields.
@dataclass
class QuerySection:
    year_hint_mode: str = "timelimit"
    year_hint_current: Optional[str] = "m"  # year == this year  → last month
    year_hint_prev: Optional[str] = "y"     # year == last year  → last year
    year_hint_older: Optional[str] = None  # year < last year  → no restriction
    auto_type_timelimit_enabled: bool = True  # infer timelimit from query type


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
class ModelsSection:
    pipeline: str = "aslm_embedding"
    enable_encoder: bool = True
    enable_decoder: bool = True
    search_device: str = "cpu"
    keep_loaded: bool = False


@dataclass
class SearchConfig:
    search: SearchSection = field(default_factory=SearchSection)
    extraction: ExtractionSection = field(default_factory=ExtractionSection)
    cache: CacheSection = field(default_factory=CacheSection)
    query: QuerySection = field(default_factory=QuerySection)
    models: ModelsSection = field(default_factory=ModelsSection)
    effort: "EffortSection" = field(default_factory=lambda: EffortSection())


_cached_config: SearchConfig | None = None

_MISSING = object()


# Coerce JSON values to optional strings (empty string → None).
def _optional_string(value: object, default: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if value == "":
        return None
    if value is _MISSING:
        return default
    return str(value)


# Load search_config.json and cache a SearchConfig singleton (custom path for tests only).
def load_search_config(path: Path | None = None) -> SearchConfig:
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
    models = raw.get("models", {})
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
            routing_profile=str(s.get("routing_profile", "stability")),
            stability_ddgs_attempts=int(s.get("stability_ddgs_attempts", 2)),
            quality_ddgs_attempts=int(s.get("quality_ddgs_attempts", 4)),
            quality_ddgs_worker_timeout=float(s.get("quality_ddgs_worker_timeout", 26.0)),
            quality_hard_timeout=float(s.get("quality_hard_timeout", 40.0)),
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
            enable_read_page_compress=bool(e.get("enable_read_page_compress", True)),
            read_page_compress_threshold_chars=int(
                e.get("read_page_compress_threshold_chars", 10_000)
            ),
            read_page_compress_target_chars=int(e.get("read_page_compress_target_chars", 10_000)),
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
            auto_type_timelimit_enabled=bool(q.get("auto_type_timelimit_enabled", True)),
        ),
        models=ModelsSection(
            pipeline=normalize_pipeline_mode(models.get("pipeline", "rules")),
            enable_encoder=bool(models.get("enable_encoder", False)),
            enable_decoder=bool(models.get("enable_decoder", False)),
            search_device=str(models.get("search_device", "cpu")),
            keep_loaded=bool(models.get("keep_loaded", False)),
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
