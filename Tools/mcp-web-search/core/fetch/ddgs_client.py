# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
DDGS (DuckDuckGo Search) provider.

Refactored from legacy deep-research/src/ddgs_client.py:
  - Removed all sys.path.insert hacks
  - Config values loaded from core.config, not from a loose config.py
  - Import of SearchResult uses core.models (no inline fallback dataclass)
  - Subprocess worker path resolved relative to this file's package
  - Snippet normalization regex moved here from engine.py

Public API
----------
DDGSClient             -- synchronous search client with retry + cache
async_ddgs_search(...) -- asyncio-friendly wrapper
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import html as html_lib
import hashlib
import json
import logging
import random
import re
import sqlite3
import sys
import time
from pathlib import Path
import threading
from threading import Lock
from typing import Optional

from core.models.search import SearchResult
from core.fetch.thread_pool import io_pool as _io_pool
from core.fetch.engine_router import (
    ENGINE_REGION_OVERRIDE,
    _quality_pass,
    _result_hash,
    get_router,
)
from core.fetch.engine_stats import Observation
from concurrent.futures import ThreadPoolExecutor, as_completed

_shared_pool: Optional[ThreadPoolExecutor] = None
_shared_pool_lock = Lock()

def _get_pool() -> ThreadPoolExecutor:
    global _shared_pool
    if _shared_pool is None:
        with _shared_pool_lock:
            if _shared_pool is None:
                # 10 workers: each search_sync sleeps 0.15–0.6s for rate-limiting,
                # so 30 workers would block the entire pool under burst load.
                pool = ThreadPoolExecutor(max_workers=10)
                atexit.register(pool.shutdown, wait=False)
                _shared_pool = pool
    return _shared_pool

logger = logging.getLogger("core.fetch.ddgs_client")


# ---------------------------------------------------------------------------
# Config defaults (overridden at runtime if core.config is available)
# ---------------------------------------------------------------------------

try:
    from core.config import load_search_config as _load_cfg
    _cfg = _load_cfg()
    DDGS_REQUEST_DELAY: tuple[float, float] = (0.15, 0.6)
    DDGS_TIMEOUT: int = int(_cfg.search.ddgs_engine_timeout)  # per-HTTP-request timeout per engine
    DDGS_MAX_RETRIES: int = 2
    DDGS_USE_SUBPROCESS: bool = True
    DDGS_WORKER_TIMEOUT: float = 25.0
except Exception:
    DDGS_REQUEST_DELAY = (0.15, 0.6)
    DDGS_TIMEOUT = 10
    DDGS_MAX_RETRIES = 2
    DDGS_USE_SUBPROCESS = True
    DDGS_WORKER_TIMEOUT = 25.0


# ---------------------------------------------------------------------------
# DDGS import
# ---------------------------------------------------------------------------

try:
    from ddgs import DDGS
    from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException
    _DDGS_AVAILABLE = True
    _EXCEPTION_CLASSES = (RatelimitException, TimeoutException, DDGSException)
except ImportError:
    try:
        from duckduckgo_search import DDGS  # type: ignore
        _DDGS_AVAILABLE = True
        _EXCEPTION_CLASSES = (Exception,)
    except ImportError:
        _DDGS_AVAILABLE = False
        _EXCEPTION_CLASSES = (Exception,)

_RETRYABLE_ERRORS = ("ssl", "eof", "connect", "connection", "timeout", "reset", "broken pipe")
_HARD_FAILURE_ERRORS = ("403", "forbidden")

# ---------------------------------------------------------------------------
# Hedged-request constants
# ---------------------------------------------------------------------------
# Backup engine fires after this many seconds if the primary hasn't responded.
# hedge_delay = clamp(primary.p95_lat * 0.8, MIN, MAX)
_HEDGE_MIN_DELAY: float = 0.5   # never hedge faster than 0.5s (avoid DDGS burst)
_HEDGE_MAX_DELAY: float = 4.0   # never wait longer than 4s before hedging
_HEDGE_DEFAULT_DELAY: float = 1.5  # used when no telemetry is available yet


# ---------------------------------------------------------------------------
# Backend presets
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Cache TTL by query type
# ---------------------------------------------------------------------------

# News/journalistic queries go stale fast; technical content stays valid longer.
_QUERY_TTL: dict[str, int] = {
    "journalistic":    300,      # 5 min  — news changes rapidly
    "finance":         600,      # 10 min — prices/news volatile
    "shopping":      3_600,      # 1 h    — prices shift but not by the minute
    "forum":         7_200,      # 2 h    — discussions evolve slowly
    "troubleshooting": 10_800,   # 3 h    — fixes get updated with new versions
    "general":       1_800,      # 30 min — default
    "medical":      43_200,      # 12 h   — guidelines change infrequently
    "technical":    86_400,      # 24 h   — docs and references rarely change
    "academic":     86_400,      # 24 h   — papers are static once published
}
_NEGATIVE_CACHE_TTL = 300     # 5 min — cache empty results to avoid hammering


def _effective_ttl(query_types: list[str], timelimit: str | None = None) -> int:
    """Return the most restrictive TTL across all matched query types.

    When a query matches both 'finance' (600s) and 'journalistic' (300s),
    the shortest TTL wins — we want the freshest possible cache.
    """
    base = min((_QUERY_TTL.get(qt, 1_800) for qt in query_types), default=1_800)
    return _timelimit_cache_ttl(timelimit, base)


def _union_preset_engines(query_types: list[str]) -> list[str]:
    """Return deduplicated union of preferred DDGS backends for all matched types.

    Preserves order: engines from the highest-priority type come first.
    Skips 'auto' entries — those mean 'no preference' and fall back to router.
    """
    seen: set[str] = set()
    engines: list[str] = []
    for qt in query_types:
        preset_str = BACKEND_PRESETS.get(qt, "")
        if not preset_str or preset_str == "auto":
            continue
        for backend in preset_str.split(","):
            backend = backend.strip()
            if backend and backend not in seen:
                seen.add(backend)
                engines.append(backend)
    return engines


# TTL caps for time-filtered queries: fresher filter → shorter cache lifetime.
# These are upper bounds — the minimum of this cap and the base TTL is used.
_TIMELIMIT_TTL: dict[str, int] = {
    "d": 300,    # day   → 5 min  (intraday results go stale fast)
    "w": 1_800,  # week  → 30 min
    "m": 7_200,  # month → 2 hr
    "y": 21_600, # year  → 6 hr
}


def _timelimit_cache_ttl(timelimit: Optional[str], base_ttl: int) -> int:
    """Return a TTL that respects the time filter's freshness requirement.

    When a time filter is active, results are expected to be more volatile,
    so the effective TTL is the minimum of the base TTL and the filter cap.
    """
    if not timelimit:
        return base_ttl
    cap = _TIMELIMIT_TTL.get(timelimit, base_ttl)
    return min(cap, base_ttl)


BACKEND_PRESETS: dict[str, str] = {
    # Authoritative, indexed, structured sources
    "technical":       "google,brave",    # large index + strong code coverage
    "troubleshooting": "google,brave",    # same — StackOverflow / GitHub issues
    "academic":        "google,brave",    # Scholar results rank well here
    "medical":         "google,brave",    # PubMed / NIH indexed by both
    # Commercial / volatile
    "finance":         "google,yahoo",    # Yahoo Finance + Google News strong here
    "shopping":        "google,yahoo",    # product pages, price aggregators
    # Community / discussion
    "forum":           "auto",            # DDG auto handles Reddit / SO well
    "journalistic":    "auto",            # DDG news ranking is decent
    "general":         "auto",
    # Language override (bypass main routing)
    "ru":              "yandex,google",
}
BACKEND_FALLBACK = ["google,brave", "mojeek", "auto"]
BACKEND_SITE_QUERY = ["yandex,yahoo", "auto"]

# ---------------------------------------------------------------------------
# Multilingual parallel-backend mapping
# ---------------------------------------------------------------------------
# Each entry: list of (ddgs_backend, ddgs_region) pairs fired in parallel.
# First non-empty result wins (same logic as the existing non-English path).
#
# Backends are chosen for stability at the given region:
#   - "duckduckgo" is always the anchor (most stable globally).
#   - "google" handles most non-Latin scripts better than yahoo.
#   - "yandex" has strong recall for ru/uk/be but tends to 403 on other langs.
#   - "yahoo" covers ja/ko/zh reasonably well.
#
# Region codes follow DDGS convention: {lang}-{country} or {lang}-{lang}.
# "wt-wt" means world-wide (no region filter).
_LANG_BACKENDS: dict[str, list[tuple[str, str]]] = {
    "ru": [("duckduckgo", "ru-ru"), ("yandex",     "ru-ru")],
    "ar": [("duckduckgo", "ar-ar"), ("google",     "ar-ar")],
    "he": [("duckduckgo", "il-he"), ("google",     "wt-wt")],
    "zh": [("duckduckgo", "cn-zh"), ("google",     "cn-zh")],
    "ja": [("duckduckgo", "jp-ja"), ("yahoo",      "jp-ja")],
    "ko": [("duckduckgo", "kr-ko"), ("yahoo",      "kr-ko")],
    "th": [("duckduckgo", "th-th"), ("google",     "th-th")],
    "hi": [("duckduckgo", "in-en"), ("google",     "in-en")],
    "el": [("duckduckgo", "gr-el"), ("google",     "wt-wt")],
}
# Fallback for languages not in the map (e.g. detected but no specific entry).
# Uses the DDGS "{lang}-{lang}" convention with two stable backends.
_LANG_BACKENDS_DEFAULT_BACKENDS = ("duckduckgo", "google")


# ---------------------------------------------------------------------------
# Snippet normalization (inlined from legacy engine.py)
# ---------------------------------------------------------------------------

_MULTI_SPACE_RE = re.compile(r"\s{2,}")
_SEPARATOR_RE = re.compile(r"\s*([|/•·])\s*")
_DASH_RE = re.compile(r"\s*([—–])\s*")
_CAMEL_BOUNDARY_RE = re.compile(r"([а-яёa-z\u00e0-\u024f])([А-ЯЁA-Z\u00c0-\u024e])")


def normalize_snippet(text: str) -> str:
    """Apply only universal cleanup without language-specific word splitting."""
    if not text:
        return text
    text = html_lib.unescape(text).replace("\u00a0", " ").strip()
    text = _CAMEL_BOUNDARY_RE.sub(r"\1 \2", text)
    text = _SEPARATOR_RE.sub(r" \1 ", text)
    text = _DASH_RE.sub(r" \1 ", text)
    return _MULTI_SPACE_RE.sub(" ", text).strip()


# ---------------------------------------------------------------------------
# DDGSClient
# ---------------------------------------------------------------------------

class DDGSClient:
    """Wrap DDGS with retry, optional SQLite cache, and proxy handling."""

    def __init__(
        self,
        proxies: Optional[list[str]] = None,
        cache_db: Optional[str] = None,
        cache_ttl: int = 3_600,
        proxy_cooldown: int = 3_600,
        request_delay: tuple[float, float] = DDGS_REQUEST_DELAY,
        timeout: int = DDGS_TIMEOUT,
        max_retries: int = DDGS_MAX_RETRIES,
    ) -> None:
        self.proxies = proxies or []
        self.cache_ttl = cache_ttl
        self.request_delay = request_delay
        self.timeout = timeout
        self.max_retries = max_retries
        self._blocked_proxies: dict[str, float] = {}
        self._proxy_cooldown = proxy_cooldown
        self._proxy_lock = Lock()
        self._cache_db = cache_db
        if cache_db:
            self._init_cache()

    # -- Proxy helpers -------------------------------------------------------

    def _get_proxy(self) -> Optional[str]:
        if not self.proxies:
            return None
        with self._proxy_lock:
            now = time.time()
            available = [
                p for p in self.proxies
                if p not in self._blocked_proxies
                or now - self._blocked_proxies[p] > self._proxy_cooldown
            ]
            return random.choice(available) if available else None

    def _block_proxy(self, proxy: str) -> None:
        with self._proxy_lock:
            self._blocked_proxies[proxy] = time.time()
            logger.warning("Proxy blocked: %s...", proxy[:30])

    # -- Cache helpers -------------------------------------------------------

    def _init_cache(self) -> None:
        with sqlite3.connect(self._cache_db) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ddgs_cache (
                    key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    ts REAL NOT NULL,
                    ttl INT NOT NULL
                )
                """
            )

    def _cache_key(self, query: str, **kwargs: object) -> str:
        from core.cache.query_normalizer import normalize_query_key
        normalized = normalize_query_key(query)
        raw = f"{normalized}|{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _cache_get(self, key: str) -> Optional[list]:
        if not self._cache_db:
            return None
        try:
            with sqlite3.connect(self._cache_db) as conn:
                row = conn.execute(
                    "SELECT data, ts, ttl FROM ddgs_cache WHERE key = ?", (key,)
                ).fetchone()
                if row and time.time() - row[1] < row[2]:
                    return json.loads(row[0])
        except Exception:
            pass
        return None

    def _cache_set(self, key: str, data: list, ttl: Optional[int] = None) -> None:
        if not self._cache_db:
            return
        try:
            with sqlite3.connect(self._cache_db) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO ddgs_cache (key, data, ts, ttl) VALUES (?, ?, ?, ?)",
                    (key, json.dumps(data, ensure_ascii=False), time.time(), ttl or self.cache_ttl),
                )
        except Exception:
            pass

    # -- Search helpers ------------------------------------------------------

    @staticmethod
    def _sanitize_query(query: str) -> str:
        query = " ".join(query.strip().split())
        if len(query) > 100:
            query = " ".join(query.split()[:10])
        return query[:120]

    def search_sync(
        self,
        query: str,
        max_results: int = 10,
        backend: str = "auto",
        region: str = "wt-wt",
        timelimit: Optional[str] = None,
        cache_ttl: Optional[int] = None,
    ) -> list[dict]:
        """Run one synchronous DDGS search with retries and caching.

        cache_ttl — override per-call TTL (seconds). Uses self.cache_ttl if None.
        Empty results are stored in a negative cache for _NEGATIVE_CACHE_TTL seconds
        to avoid hammering an engine that just returned nothing.
        """
        if not _DDGS_AVAILABLE:
            logger.error("ddgs is not installed: pip install ddgs")
            return []

        query = self._sanitize_query(query)
        if not query:
            return []

        cache_key = self._cache_key(
            query,
            max_results=max_results,
            backend=backend,
            region=region,
            timelimit=timelimit or "",
        )
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        for attempt in range(self.max_retries):
            proxy = self._get_proxy()
            try:
                if attempt > 0:
                    delay = min(2 * attempt + random.uniform(0, 0.5), 4)
                    time.sleep(delay)
                else:
                    time.sleep(random.uniform(*self.request_delay))

                ddgs = DDGS(proxy=proxy, timeout=self.timeout)
                ddgs_kwargs: dict = {
                    "max_results": max_results,
                    "backend": backend,
                    "region": region,
                }
                if timelimit:
                    ddgs_kwargs["timelimit"] = timelimit

                try:
                    results = ddgs.text(query, **ddgs_kwargs)
                except TypeError:
                    ddgs_kwargs.pop("timelimit", None)
                    results = ddgs.text(query, **ddgs_kwargs)

                results = results or []
                ttl = cache_ttl if cache_ttl is not None else self.cache_ttl
                if results:
                    self._cache_set(cache_key, results, ttl=ttl)
                else:
                    # Negative cache: don't retry same engine for _NEGATIVE_CACHE_TTL s
                    self._cache_set(cache_key, [], ttl=_NEGATIVE_CACHE_TTL)
                return results

            except _EXCEPTION_CLASSES as error:
                message = str(error)
                log_level = logging.DEBUG if "No results found" in message else logging.WARNING
                logger.log(log_level, "DDGS attempt %s/%s: %s", attempt + 1, self.max_retries, error)
                if any(marker in message.lower() for marker in _HARD_FAILURE_ERRORS):
                    # Hard provider blocks like HTTP 403 won't recover within the
                    # same request; avoid wasting retries and cache the miss briefly.
                    self._cache_set(cache_key, [], ttl=_NEGATIVE_CACHE_TTL)
                    break
                if proxy and "ratelimit" in message.lower():
                    self._block_proxy(proxy)
            except Exception as error:
                message = str(error).lower()
                if any(kw in message for kw in _RETRYABLE_ERRORS):
                    logger.warning("DDGS attempt %s/%s: %s", attempt + 1, self.max_retries, error)
                else:
                    logger.debug("DDGS unexpected error: %s", error)
                    break

        return []

    def search_to_results(
        self,
        query: str,
        max_results: int = 10,
        backend: str = "auto",
        region: str = "wt-wt",
        timelimit: Optional[str] = None,
        cache_ttl: Optional[int] = None,
    ) -> list[SearchResult]:
        """Convert raw DDGS rows into SearchResult objects."""
        raw = self.search_sync(
            query=query,
            max_results=max_results,
            backend=backend,
            region=region,
            timelimit=timelimit,
            cache_ttl=cache_ttl,
        )
        results: list[SearchResult] = []
        for item in raw:
            url = item.get("href") or item.get("url") or ""
            if not url:
                continue
            results.append(
                SearchResult(
                    url=url,
                    title=normalize_snippet(item.get("title", "")),
                    snippet=normalize_snippet(item.get("body", "") or item.get("snippet", "")),
                    engine=f"ddgs:{backend}",
                )
            )
        return results

    def search_with_fallback(
        self,
        query: str,
        max_results: int = 10,
        query_type: str = "general",
        query_types: Optional[list[str]] = None,
        lang: str = "en",
        timelimit: Optional[str] = None,
        hedge_count: int = 2,
    ) -> list[SearchResult]:
        """Try engines via router until one returns results.

        query_types — when provided (multi-type classification), backend
        presets and TTL are derived as the union / minimum across all types.
        query_type (single) is used as the primary label for logging only.

        Special cases (site: queries, non-en lang) bypass the router and use
        static backend lists, since the router only tracks single-engine
        performance and these queries have different engine preferences.
        """
        # Normalise: use query_types when available, fall back to single type
        _qtypes: list[str] = query_types if query_types else [query_type]
        # site: queries — static list, bypass router
        if query.lstrip().lower().startswith("site:"):
            for backend in BACKEND_SITE_QUERY:
                results = self.search_to_results(query, max_results, backend=backend, timelimit=timelimit)
                if results:
                    return results
            return []

        # Non-English queries — run backends in parallel and take the first
        # with results.  Backend pairs are language-specific (see _LANG_BACKENDS).
        if lang != "en":
            if lang in _LANG_BACKENDS:
                parallel_backends = _LANG_BACKENDS[lang]
            else:
                # Unknown non-English lang: use DDGS convention region + two
                # backends that handle most scripts without hard 403s.
                region = f"{lang}-{lang}"
                parallel_backends = [
                    (_LANG_BACKENDS_DEFAULT_BACKENDS[0], region),
                    (_LANG_BACKENDS_DEFAULT_BACKENDS[1], region),
                ]
                logger.debug(
                    "multilingual: no entry for lang=%r, using default backends region=%s",
                    lang, region,
                )

            logger.debug(
                "multilingual: lang=%s backends=%s",
                lang, [(be, reg) for be, reg in parallel_backends],
            )
            fast_client = DDGSClient(
                request_delay=(0.0, 0.2),
                max_retries=1,
                cache_db=self._cache_db,
                cache_ttl=self.cache_ttl,
            )
            pool = _get_pool()
            futures = {
                pool.submit(
                    fast_client.search_to_results, query, max_results,
                    backend=be, region=reg, timelimit=timelimit,
                ): be
                for be, reg in parallel_backends
            }
            result: list[SearchResult] = []
            try:
                for fut in as_completed(futures, timeout=self.timeout):
                    try:
                        res = fut.result()
                        if res:
                            result = res
                            break
                    except Exception:
                        pass
            except TimeoutError:
                logger.debug("multilingual parallel search timed out after %ss", self.timeout)
                # no pool.shutdown anymore
            return result

        # General queries — router-driven hedged search.
        #
        # Instead of a sequential fallback loop, we fire engines with a
        # staggered start:
        #
        #   t=0          → primary fires
        #   t=hedge_delay → backup fires IF primary hasn't returned yet
        #   t=2*hedge_delay → tertiary fires IF neither has returned
        #
        # hedge_delay is adaptive: 80% of primary's p75 latency, bounded to
        # [_HEDGE_MIN_DELAY, _HEDGE_MAX_DELAY]. No telemetry yet → default 1s.
        #
        # A threading.Event lets already-sleeping backup threads cancel
        # immediately when the primary wins, so they don't waste DDGS quota.
        router = get_router()
        # Use the most restrictive TTL across all matched query types
        ttl = _effective_ttl(_qtypes, timelimit)

        # hedge_count controls how many DDGS backends fire in parallel.
        # Callers reduce this when hosted API engines already cover the query.
        hedge_count = max(1, hedge_count)

        # Bias engine selection toward union of BACKEND_PRESETS for all
        # matched query types, respecting the router's circuit-breaker state.
        preset_engines = _union_preset_engines(_qtypes)
        preferred = [
            e for e in preset_engines
            if e in router.registry and not router.registry[e].is_tripped
        ]

        if preferred:
            router_fill = router.pick_pool(n=hedge_count + len(preferred))
            merged = list(dict.fromkeys(preferred + router_fill))
            engines = merged[:hedge_count]
            logger.debug(
                "preset routing: types=%s preferred=%s engines=%s",
                _qtypes, preset_engines, engines,
            )
        else:
            engines = router.pick_pool(n=hedge_count)

        # Add one more tertiary hedge only when full hedging is requested
        if hedge_count >= 2:
            extra = router.available(exclude=set(engines))
            if extra:
                engines = (engines + [extra[0]])[:3]

        # Adaptive hedge delay based on primary engine's p75 latency
        primary_stats = router.registry.get(engines[0])
        if primary_stats and primary_stats.latencies:
            p75_lat = primary_stats.p95_latency  # use p95 for conservative threshold
            hedge_delay = max(_HEDGE_MIN_DELAY, min(_HEDGE_MAX_DELAY, p75_lat * 0.8))
        else:
            hedge_delay = _HEDGE_DEFAULT_DELAY

        logger.debug(
            "hedged_search: engines=%s hedge_delay=%.2fs",
            engines, hedge_delay,
        )

        stop = threading.Event()

        def _hedged_search(engine: str, start_delay: float) -> list:
            """Run one search attempt after an optional stagger delay."""
            if start_delay > 0 and stop.wait(timeout=start_delay):
                # stop was signalled before our delay expired → another engine won
                return []
            if stop.is_set():
                return []

            region = ENGINE_REGION_OVERRIDE.get(engine, "wt-wt")
            t0 = time.perf_counter()
            try:
                res = self.search_to_results(
                    query, max_results,
                    backend=engine,
                    region=region,
                    timelimit=timelimit,
                    cache_ttl=ttl,
                )
            except Exception:
                res = []
            latency = time.perf_counter() - t0

            raw = [{"body": r.snippet, "href": r.url} for r in res]
            router.record(engine, Observation(
                ts=time.time(),
                latency=latency,
                success=bool(res),
                result_count=len(res),
                quality_pass=_quality_pass(raw),
                result_hash=_result_hash(raw),
            ))
            return res

        pool = _get_pool()
        futs = {
            pool.submit(_hedged_search, eng, i * hedge_delay): eng
            for i, eng in enumerate(engines)
        }
        hedged_result: list[SearchResult] = []
        overall_timeout = self.timeout + (hedge_delay * max(0, len(engines) - 1)) + 0.5
        try:
            for fut in as_completed(futs, timeout=overall_timeout):
                try:
                    results = fut.result()
                except Exception:
                    results = []
                if results:
                    stop.set()  # cancel sleeping backup threads
                    hedged_result = results
                    break
        except TimeoutError:
            logger.debug(
                "hedged_search timed out after %.2fs (engine timeout=%ss, engines=%s, hedge_delay=%.2fs)",
                overall_timeout,
                self.timeout,
                engines,
                hedge_delay,
            )
        finally:
            stop.set()
            # no pool.shutdown anymore

        return hedged_result


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_client: Optional[DDGSClient] = None
_client_lock = Lock()

def get_ddgs_client(
    proxies: Optional[list[str]] = None,
    cache_db: Optional[str] = None,
) -> DDGSClient:
    """Return the lazily initialized global DDGS client."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = DDGSClient(
                    proxies=proxies or [],
                    cache_db=cache_db,
                    cache_ttl=3_600,
                    request_delay=DDGS_REQUEST_DELAY,
                    timeout=DDGS_TIMEOUT,
                    max_retries=DDGS_MAX_RETRIES,
                )
    return _client


# ---------------------------------------------------------------------------
# Subprocess worker helpers (for hard-kill on timeout)
# ---------------------------------------------------------------------------

_WORKER_SCRIPT = Path(__file__).parent / "_ddgs_worker.py"


def _query_preview(query: str, limit: int = 96) -> str:
    compact = " ".join((query or "").split())
    return compact if len(compact) <= limit else compact[: max(0, limit - 3)].rstrip() + "..."




def _deserialize_results(payload: list[dict]) -> list[SearchResult]:
    results: list[SearchResult] = []
    for item in payload or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        results.append(
            SearchResult(
                url=url,
                title=str(item.get("title") or ""),
                snippet=str(item.get("snippet") or ""),
                engine=str(item.get("engine") or ""),
                trust_tier=str(item.get("trust_tier") or "?"),
                score=float(item.get("score") or 0.0),
                method_hint=str(item.get("method_hint") or ""),
            )
        )
    return results


# ---------------------------------------------------------------------------
# Async interface
# ---------------------------------------------------------------------------

async def async_ddgs_search(
    query: str,
    max_results: int = 10,
    query_type: str = "general",
    query_types: Optional[list[str]] = None,
    lang: str = "en",
    timelimit: Optional[str] = None,
    use_subprocess: Optional[bool] = None,
    worker_timeout: Optional[float] = None,
    hedge_count: int = 2,
) -> list[SearchResult]:
    """Run DDGS search for asyncio callers with optional hard-kill subprocess.

    query_types — when provided (multi-type classification), backend presets
    and TTL are derived as the union / minimum across all types.
    hedge_count — number of DDGS backends to fire in parallel (hedging).
    Pass 1 when hosted API engines are already covering the query so DDGS
    doesn't fire redundant parallel backends.
    """
    client = get_ddgs_client()
    use_subprocess = DDGS_USE_SUBPROCESS if use_subprocess is None else use_subprocess
    worker_timeout = DDGS_WORKER_TIMEOUT if worker_timeout is None else worker_timeout

    if use_subprocess and _WORKER_SCRIPT.exists():
        request_payload = {
            "query": query,
            "max_results": max_results,
            "query_type": query_type,
            "query_types": query_types,
            "lang": lang,
            "timelimit": timelimit,
            "hedge_count": hedge_count,
            "proxies": list(client.proxies or []),
            "cache_db": client._cache_db,
            "cache_ttl": int(client.cache_ttl),
            "proxy_cooldown": int(client._proxy_cooldown),
            "request_delay": [float(client.request_delay[0]), float(client.request_delay[1])],
            "timeout": int(client.timeout),
            "max_retries": int(client.max_retries),
        }

        proc: Optional[asyncio.subprocess.Process] = None
        stdout: Optional[bytes] = None
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-u", str(_WORKER_SCRIPT),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(json.dumps(request_payload, ensure_ascii=False).encode()),
                timeout=max(0.1, float(worker_timeout)),
            )

        except asyncio.TimeoutError:
            logger.warning(
                "DDGS worker timeout after %.1fs for query=%r",
                worker_timeout, _query_preview(query),
            )
            return []

        except asyncio.CancelledError:
            # Propagate cancellation after cleanup (handled in finally).
            logger.debug("DDGS worker cancelled for query=%r", _query_preview(query))
            raise

        except Exception as exc:
            logger.warning(
                "DDGS worker error for query=%r: %s", _query_preview(query), exc
            )
            return []

        finally:
            # --- Guaranteed subprocess cleanup ---
            # This block runs on normal exit, TimeoutError, CancelledError, and
            # any other exception.  proc.wait() (not communicate) is used so we
            # don't touch the already-consumed stdio streams.
            # Without this, killed or orphaned subprocesses become zombies on
            # Unix (no waitpid) or hold handles on Windows.
            if proc is not None and proc.returncode is None:
                with contextlib.suppress(Exception):
                    proc.kill()
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(proc.wait(), timeout=3.0)

        # --- Parse result ---
        if proc.returncode not in (0, None):
            logger.warning(
                "DDGS worker exited code %s for query=%r",
                proc.returncode, _query_preview(query),
            )
            return []

        stdout_text = (stdout or b"").decode("utf-8", errors="replace").strip()
        if not stdout_text:
            logger.warning("DDGS worker empty stdout for query=%r", _query_preview(query))
            return []
        try:
            payload = json.loads(stdout_text)
        except Exception as exc:
            logger.warning("DDGS worker invalid JSON for query=%r: %s", _query_preview(query), exc)
            return []
        if not payload.get("ok", False):
            logger.warning(
                "DDGS worker failed for query=%r: %s",
                _query_preview(query),
                payload.get("error") or "unknown",
            )
            return []
        return _deserialize_results(payload.get("results") or [])

    # Executor fallback (when subprocess is disabled or worker script missing)
    def _sync() -> list[SearchResult]:
        return client.search_with_fallback(
            query=query,
            max_results=max_results,
            query_type=query_type,
            query_types=query_types,
            lang=lang,
            timelimit=timelimit,
            hedge_count=hedge_count,
        )

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_io_pool, _sync)
