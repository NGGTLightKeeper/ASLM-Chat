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
    search_ttl_seconds: int = 21_600        # 6 h — flat TTL for the query-results cache
    search_negative_ttl_seconds: int = 300  # 5 min — empty/failed result sets
    page_ttl_seconds: int = 86_400
    repeat_block_window_seconds: int = 30   # identical query within this → hard block
    seen_source_window_seconds: int = 30    # drop sources served to the model within this
    prefetch_max_urls: int = 4              # top uncached result URLs warmed per search (0 = off)


# Year tokens in queries: timelimit (default), strip, or none — see year_hint_* fields.
@dataclass
class QuerySection:
    year_hint_mode: str = "timelimit"
    year_hint_current: Optional[str] = "m"  # year == this year  → last month
    year_hint_prev: Optional[str] = "y"     # year == last year  → last year
    year_hint_older: Optional[str] = None  # year < last year  → no restriction
    auto_type_timelimit_enabled: bool = True  # infer timelimit from query type


# Warm-browser layer. Two independent axes: where the browser is
# allowed as a fallback (browser_fallback) and which backend serves it (browser_backend).
@dataclass
class BrowserSection:
    browser_fallback: str = "page"      # off | page (read_page only) | full (+ blocked SERP engines)
    browser_backend: str = "warm"       # warm (cloakbrowser daemon) | legacy (camoufox subprocess)
    daemon_url: str = "http://127.0.0.1:8765"
    engine: str = "chromium"            # warm backend is chromium-only by design
    autostart_daemon: bool = True       # spawn the daemon lazily on the first tool call
    # Daemon self-shuts-down after this many idle seconds (no fetch); 0 = eternal (run
    # until the task is killed). Default 30 min so a tool-call-spawned daemon does not
    # linger forever once searches stop.
    daemon_idle_shutdown_sec: float = 1800.0
    headless: bool = True
    humanize: bool = False
    proxy: str = ""
    nav_timeout: float = 30.0           # per-page navigation timeout (seconds)
    wait: float = 3.0                   # post-load text-settle wait (seconds)
    fetch_timeout: float = 45.0         # client-side ceiling for one /fetch round-trip
    # Recycle thresholds (passed to the daemon; enforced daemon-side).
    max_requests: int = 40
    max_age_sec: float = 900.0
    max_rss_mb: int = 2048              # RSS of the browser process tree → checkpoint + respawn
    checkpoint_interval: float = 30.0   # idle storageState checkpoint cadence (seconds)


@dataclass
class ModelsSection:
    pipeline: str = "aslm_embedding"
    enable_decoder: bool = True       # decoder content-stage re-ranker (high effort only, CPU)
    decoder_model_dir: str = ""       # export dir; empty → <root>/models/aslm_embedding_decoder
    decoder_weight: float = 0.45      # blend: final = (1-w)*rules_score + w*decoder_score
    keep_loaded: bool = False


@dataclass
class SearchConfig:
    search: SearchSection = field(default_factory=SearchSection)
    extraction: ExtractionSection = field(default_factory=ExtractionSection)
    cache: CacheSection = field(default_factory=CacheSection)
    query: QuerySection = field(default_factory=QuerySection)
    models: ModelsSection = field(default_factory=ModelsSection)
    browser: BrowserSection = field(default_factory=BrowserSection)


_cached_config: SearchConfig | None = None

_MISSING = object()


# Coerce a value to one of an allowed set (case-insensitive), falling back on default.
def _one_of(value: object, allowed: set[str], default: str) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in allowed:
        return candidate
    if value not in (None, ""):
        logger.warning("config: invalid value %r (allowed: %s) — using %r", value, sorted(allowed), default)
    return default


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
    b = raw.get("browser", {})

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
            search_ttl_seconds=int(c.get("search_ttl_seconds", 21_600)),
            search_negative_ttl_seconds=int(c.get("search_negative_ttl_seconds", 300)),
            page_ttl_seconds=int(c.get("page_ttl_seconds", 86_400)),
            repeat_block_window_seconds=int(c.get("repeat_block_window_seconds", 30)),
            seen_source_window_seconds=int(c.get("seen_source_window_seconds", 30)),
            prefetch_max_urls=int(c.get("prefetch_max_urls", 4)),
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
            enable_decoder=bool(models.get("enable_decoder", False)),
            decoder_model_dir=str(models.get("decoder_model_dir", "")),
            decoder_weight=float(models.get("decoder_weight", 0.45)),
            keep_loaded=bool(models.get("keep_loaded", False)),
        ),
        browser=BrowserSection(
            browser_fallback=_one_of(
                b.get("browser_fallback", "page"), {"off", "page", "full"}, "page"
            ),
            browser_backend=_one_of(
                b.get("browser_backend", "warm"), {"warm", "legacy"}, "warm"
            ),
            daemon_url=str(b.get("daemon_url", "http://127.0.0.1:8765")),
            engine=str(b.get("engine", "chromium")),
            autostart_daemon=bool(b.get("autostart_daemon", True)),
            daemon_idle_shutdown_sec=float(b.get("daemon_idle_shutdown_sec", 1800.0)),
            headless=bool(b.get("headless", True)),
            humanize=bool(b.get("humanize", False)),
            proxy=str(b.get("proxy", "")),
            nav_timeout=float(b.get("nav_timeout", 30.0)),
            wait=float(b.get("wait", 3.0)),
            fetch_timeout=float(b.get("fetch_timeout", 45.0)),
            max_requests=int(b.get("max_requests", 40)),
            max_age_sec=float(b.get("max_age_sec", 900.0)),
            max_rss_mb=int(b.get("max_rss_mb", 2048)),
            checkpoint_interval=float(b.get("checkpoint_interval", 30.0)),
        ),
    )

    if path is None:
        _cached_config = config
    return config
