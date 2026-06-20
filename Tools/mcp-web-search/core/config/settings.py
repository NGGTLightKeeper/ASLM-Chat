# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


logger = logging.getLogger("config.search")

_CONFIG_PATH = Path(__file__).parent / "search_config.json"

# Warm-browser daemon default port. ASLM assigns one in its port range and passes it via
# ASLM_BROWSER_DAEMON_PORT; standalone runs fall back to 20004 (the module's declared default).
_DEFAULT_DAEMON_PORT = 20004


def _default_daemon_url() -> str:
    raw = (os.environ.get("ASLM_BROWSER_DAEMON_PORT") or "").strip()
    try:
        port = int(raw) if raw else _DEFAULT_DAEMON_PORT
    except ValueError:
        port = _DEFAULT_DAEMON_PORT
    if not (0 < port <= 65535):
        port = _DEFAULT_DAEMON_PORT
    return f"http://127.0.0.1:{port}"


# Typed config dataclasses (loaded from search_config.json).
@dataclass
class SearchSection:
    # NOTE: the new streaming pipeline hardcodes per-effort budgets in EFFORT_PROFILES;
    # only the fields below are still read. The legacy DDGS/preview/quality-worker knobs
    # (ddgs_*, preview_fetch_*, quality_ddgs_*, routing_profile, auto_scrape_preview, …)
    # were removed 2026-06-20 — they had zero readers after the rewrite.
    tls_verify: bool = True        # set False only behind corporate MITM proxies
    max_results: int = 10
    batch_query_limit: int = 10    # read_page multi-URL batch cap (mcp-server)
    prefetch_fetch_timeout: float = 8.0
    preview_max_chars: int = 4_000     # per-source chars in model_context
    total_context_budget: int = 40_000  # max chars in total search output (0 = no limit)


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


# Warm-browser layer (cloakbrowser daemon). browser_fallback controls where the
# browser is allowed as a fallback; the backend is always the warm chromium daemon.
@dataclass
class BrowserSection:
    browser_fallback: str = "page"      # off | page (read_page only) | full (+ blocked SERP engines)
    daemon_url: str = field(default_factory=_default_daemon_url)
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
class SearchConfig:
    search: SearchSection = field(default_factory=SearchSection)
    extraction: ExtractionSection = field(default_factory=ExtractionSection)
    cache: CacheSection = field(default_factory=CacheSection)
    query: QuerySection = field(default_factory=QuerySection)
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
    b = raw.get("browser", {})

    config = SearchConfig(
        search=SearchSection(
            tls_verify=bool(s.get("tls_verify", True)),
            max_results=int(s.get("max_results", 10)),
            batch_query_limit=int(s.get("batch_query_limit", 10)),
            prefetch_fetch_timeout=float(s.get("prefetch_fetch_timeout", 8.0)),
            preview_max_chars=int(s.get("preview_max_chars", 4_000)),
            total_context_budget=int(s.get("total_context_budget", 40_000)),
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
        ),
        browser=BrowserSection(
            browser_fallback=_one_of(
                b.get("browser_fallback", "page"), {"off", "page", "full"}, "page"
            ),
            daemon_url=str(b.get("daemon_url") or _default_daemon_url()),
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
