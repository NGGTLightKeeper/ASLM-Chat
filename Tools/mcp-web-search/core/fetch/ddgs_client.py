# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

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
import tempfile
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

# Dedicated thread pool for DDGS sync search (rate-limited sleeps).
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


try:
    from ddgs import DDGS
    from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException
    _DDGS_AVAILABLE = True
    _EXCEPTION_CLASSES = (RatelimitException, TimeoutException, DDGSException)
except ImportError:
    _DDGS_AVAILABLE = False
    _EXCEPTION_CLASSES = (Exception,)

_RETRYABLE_ERRORS = ("ssl", "eof", "connect", "connection", "timeout", "reset", "broken pipe")
_HARD_FAILURE_ERRORS = ("403", "forbidden")
_OPERATOR_TOKEN_RE = re.compile(r"(?<!\S)(?:-?site:[^\s]+|inurl:[^\s]+|intitle:[^\s]+|filetype:[^\s]+|(?:OR|\|))(?=\s|$)", re.IGNORECASE)
_LEXICAL_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]{2,}|[А-Яа-яЁё0-9_\-]{2,}")

# Backup engine fires after hedge_delay if primary hasn't responded (see search_with_fallback).
_HEDGE_MIN_DELAY: float = 0.5   # never hedge faster than 0.5s (avoid DDGS burst)
_HEDGE_MAX_DELAY: float = 4.0   # never wait longer than 4s before hedging
_HEDGE_DEFAULT_DELAY: float = 1.5  # used when no telemetry is available yet


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


# Shortest TTL across matched query types (e.g. finance + journalistic → 300s).
def _effective_ttl(query_types: list[str], timelimit: str | None = None) -> int:
    base = min((_QUERY_TTL.get(qt, 1_800) for qt in query_types), default=1_800)
    return _timelimit_cache_ttl(timelimit, base)


# Union of BACKEND_PRESETS engines for all matched types (skips "auto").
def _union_preset_engines(query_types: list[str]) -> list[str]:
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
_PARTIAL_BUFFER_LOCK = Lock()


# Serialize SearchResult list for partial-timeout buffer file.
def _serialise_results(results: list[SearchResult]) -> list[dict]:
    return [
        {
            "url": r.url,
            "title": r.title,
            "snippet": r.snippet,
            "engine": r.engine,
            "trust_tier": r.trust_tier,
            "score": float(r.score or 0.0),
            "method_hint": r.method_hint,
            "published_date": r.published_date,
            "pdf_url": r.pdf_url,
        }
        for r in results
    ]


# Merge and persist partial hedged-search results for worker timeout recovery.
def _write_partial_results(path: str | None, results: list[SearchResult]) -> None:
    if not path or not results:
        return
    try:
        with _PARTIAL_BUFFER_LOCK:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            existing: list[dict] = []
            if target.exists():
                with contextlib.suppress(Exception):
                    payload = json.loads(target.read_text(encoding="utf-8"))
                    existing = list(payload.get("results") or [])

            merged: list[dict] = []
            seen_urls: set[str] = set()
            for item in [*existing, *_serialise_results(results)]:
                url = str(item.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                merged.append(item)

            tmp = target.with_suffix(target.suffix + ".tmp")
            payload = {
                "ok": True,
                "partial": True,
                "ts": time.time(),
                "results": merged,
            }
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.replace(target)
    except Exception as exc:
        logger.debug("ddgs partial buffer write failed path=%r err=%s", path, exc)


# Load partial results written before a subprocess worker timed out.
def _read_partial_results(path: str | None) -> list[SearchResult]:
    if not path:
        return []
    try:
        target = Path(path)
        if not target.exists():
            return []
        payload = json.loads(target.read_text(encoding="utf-8"))
        results = _deserialize_results(payload.get("results") or [])
        for result in results:
            result.method_hint = "|".join(
                part for part in [result.method_hint, "partial_timeout"] if part
            )
        return results
    except Exception as exc:
        logger.debug("ddgs partial buffer read failed path=%r err=%s", path, exc)
        return []


# Cap cache TTL when a timelimit filter is active (fresher results expected).
def _timelimit_cache_ttl(timelimit: Optional[str], base_ttl: int) -> int:
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


_MULTI_SPACE_RE = re.compile(r"\s{2,}")
_SEPARATOR_RE = re.compile(r"\s*([|/•·])\s*")
_DASH_RE = re.compile(r"\s*([—–])\s*")
_CAMEL_BOUNDARY_RE = re.compile(r"([а-яёa-z\u00e0-\u024f])([А-ЯЁA-Z\u00c0-\u024e])")


# Universal snippet cleanup (no language-specific tokenization).
def normalize_snippet(text: str) -> str:
    if not text:
        return text
    text = html_lib.unescape(text).replace("\u00a0", " ").strip()
    text = _CAMEL_BOUNDARY_RE.sub(r"\1 \2", text)
    text = _SEPARATOR_RE.sub(r" \1 ", text)
    text = _DASH_RE.sub(r" \1 ", text)
    return _MULTI_SPACE_RE.sub(" ", text).strip()


# DDGS sometimes prepends a date to the snippet body: "Feb 13, 2025 · text..."
# No space before year is common: "Aug 15,2025 ·" — hence \s* before \d{4}.
_SNIPPET_DATE_RE = re.compile(
    r"^([A-Z][a-z]{2}\.?\s+\d{1,2},?\s*\d{4}|\d{4}-\d{2}-\d{2})\s*[·—–\-]"
)


# Parse leading date prefix from a DDGS snippet string.
def _extract_snippet_date(snippet: str) -> str:
    m = _SNIPPET_DATE_RE.match(snippet or "")
    return m.group(1).rstrip(",").strip() if m else ""


# DDGS wrapper with retry, SQLite cache, and proxy rotation.
class DDGSClient:

    # Configure proxies, cache, delays, and retry policy.
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

    # Pick a random proxy not in cooldown.
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

    # Mark proxy as rate-limited until cooldown expires.
    def _block_proxy(self, proxy: str) -> None:
        with self._proxy_lock:
            self._blocked_proxies[proxy] = time.time()
            logger.warning("Proxy blocked: %s...", proxy[:30])

    # Create SQLite cache table if missing.
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

    # SHA-256 key from normalized query plus search parameters.
    def _cache_key(self, query: str, **kwargs: object) -> str:
        from core.cache.query_normalizer import normalize_exact_query_key, normalize_query_key
        normalized = normalize_query_key(query)
        exact = normalize_exact_query_key(query)
        raw = f"{normalized}|{json.dumps(kwargs, sort_keys=True)}"
        raw = f"{exact}|{raw}"
        return hashlib.sha256(raw.encode()).hexdigest()

    # Return cached raw DDGS rows if still within TTL.
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
        except Exception as _e:
            logger.debug("ddgs cache_get failed: %s", _e)
        return None

    # Store raw DDGS rows with optional per-entry TTL.
    def _cache_set(self, key: str, data: list, ttl: Optional[int] = None) -> None:
        if not self._cache_db:
            return
        try:
            with sqlite3.connect(self._cache_db) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO ddgs_cache (key, data, ts, ttl) VALUES (?, ?, ?, ?)",
                    (key, json.dumps(data, ensure_ascii=False), time.time(), ttl or self.cache_ttl),
                )
        except Exception as _e:
            logger.debug("ddgs cache_set failed: %s", _e)

    # Truncate and collapse whitespace on user query.
    @staticmethod
    def _sanitize_query(query: str) -> str:
        query = " ".join(query.strip().split())
        if len(query) > 100:
            query = " ".join(query.split()[:10])
        return query[:120]

    # Progressively simpler query variants for zero-result fallback.
    @staticmethod
    def _degraded_query_variants(query: str) -> list[str]:
        base = " ".join(str(query or "").split()).strip()
        if not base:
            return []
        variants: list[str] = []

        # Append unique simplified variant strings.
        def add_variant(value: str) -> None:
            candidate = " ".join(str(value or "").split()).strip()
            if candidate and candidate != base and candidate not in variants:
                variants.append(candidate)

        unquoted = re.sub(r"[\"'`]+", " ", base)
        add_variant(unquoted)
        no_ops = _OPERATOR_TOKEN_RE.sub(" ", unquoted)
        no_ops = re.sub(r"(?<!\S)-[^\s]+", " ", no_ops)
        add_variant(no_ops)

        lexical = _LEXICAL_TOKEN_RE.findall(no_ops)
        if lexical:
            add_variant(" ".join(lexical[:4]))
            add_variant(" ".join(lexical[:2]))
        return variants

    # One synchronous DDGS search with retries, cache, and negative cache on empty.
    def search_sync(
        self,
        query: str,
        max_results: int = 10,
        backend: str = "auto",
        region: str = "wt-wt",
        timelimit: Optional[str] = None,
        cache_ttl: Optional[int] = None,
    ) -> list[dict]:
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

    # search_sync mapped to SearchResult models with normalized snippets.
    def search_to_results(
        self,
        query: str,
        max_results: int = 10,
        backend: str = "auto",
        region: str = "wt-wt",
        timelimit: Optional[str] = None,
        cache_ttl: Optional[int] = None,
    ) -> list[SearchResult]:
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
            snippet = normalize_snippet(item.get("body", "") or item.get("snippet", ""))
            results.append(
                SearchResult(
                    url=url,
                    title=normalize_snippet(item.get("title", "")),
                    snippet=snippet,
                    engine=f"ddgs:{backend}",
                    published_date=_extract_snippet_date(snippet),
                )
            )
        return results

    # Router-driven hedged search; site: and non-en lang use static backend lists.
    def search_with_fallback(
        self,
        query: str,
        max_results: int = 10,
        query_type: str = "general",
        query_types: Optional[list[str]] = None,
        lang: str = "en",
        timelimit: Optional[str] = None,
        hedge_count: int = 2,
        partial_buffer_path: str | None = None,
    ) -> list[SearchResult]:
        # Normalise: use query_types when available, fall back to single type
        _qtypes: list[str] = query_types if query_types else [query_type]
        # site: queries — static list, bypass router
        if query.lstrip().lower().startswith("site:"):
            for backend in BACKEND_SITE_QUERY:
                results = self.search_to_results(query, max_results, backend=backend, timelimit=timelimit)
                if results:
                    _write_partial_results(partial_buffer_path, results)
                    return results
            for variant in self._degraded_query_variants(query):
                for backend in BACKEND_FALLBACK:
                    results = self.search_to_results(variant, max_results, backend=backend, timelimit=None)
                    if results:
                        logger.info("ddgs fallback hit (site query) variant=%r backend=%s", variant, backend)
                        _write_partial_results(partial_buffer_path, results)
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
                            _write_partial_results(partial_buffer_path, res)
                            result = res
                            break
                    except Exception as _e:
                        logger.debug("multilingual future failed: %s", _e)
            except TimeoutError:
                logger.debug("multilingual parallel search timed out after %ss", self.timeout)
                # no pool.shutdown anymore
            if result:
                return result
            for variant in self._degraded_query_variants(query):
                for backend in BACKEND_FALLBACK:
                    degraded = self.search_to_results(
                        variant,
                        max_results,
                        backend=backend,
                        region="wt-wt",
                        timelimit=None,
                    )
                    if degraded:
                        logger.info("ddgs fallback hit (multilingual) variant=%r backend=%s", variant, backend)
                        _write_partial_results(partial_buffer_path, degraded)
                        return degraded
            return []

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

        # Run one hedged engine after optional stagger delay.
        def _hedged_search(engine: str, start_delay: float) -> list:
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
                if res:
                    _write_partial_results(partial_buffer_path, res)
            except Exception as _e:
                logger.debug("hedged search engine=%s failed: %s", engine, _e)
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
                except Exception as _e:
                    logger.debug("hedged future failed: %s", _e)
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

        if hedged_result:
            _write_partial_results(partial_buffer_path, hedged_result)
            return hedged_result

        for variant in self._degraded_query_variants(query):
            for backend in BACKEND_FALLBACK:
                degraded = self.search_to_results(
                    variant,
                    max_results,
                    backend=backend,
                    region="wt-wt",
                    timelimit=None,
                )
                if degraded:
                    logger.info("ddgs fallback hit variant=%r backend=%s", variant, backend)
                    _write_partial_results(partial_buffer_path, degraded)
                    return degraded
        return []


_client: Optional[DDGSClient] = None
_client_lock = Lock()

# Lazily initialized global DDGS client singleton.
def get_ddgs_client(
    proxies: Optional[list[str]] = None,
    cache_db: Optional[str] = None,
) -> DDGSClient:
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


_WORKER_SCRIPT = Path(__file__).parent / "_ddgs_worker.py"


# Truncate query for log messages.
def _query_preview(query: str, limit: int = 96) -> str:
    compact = " ".join((query or "").split())
    return compact if len(compact) <= limit else compact[: max(0, limit - 3)].rstrip() + "..."




# Rebuild SearchResult list from worker subprocess JSON payload.
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
                published_date=str(item.get("published_date") or ""),
            )
        )
    return results


# Async DDGS search; optional isolated subprocess for hard-kill on timeout.
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
    engine_timeout: Optional[int] = None,
    max_retries: Optional[int] = None,
) -> list[SearchResult]:
    client = get_ddgs_client()
    use_subprocess = DDGS_USE_SUBPROCESS if use_subprocess is None else use_subprocess
    worker_timeout = DDGS_WORKER_TIMEOUT if worker_timeout is None else worker_timeout

    if use_subprocess and _WORKER_SCRIPT.exists():
        partial_buffer_path: str | None = None
        with tempfile.NamedTemporaryFile(
            prefix="ddgs_partial_",
            suffix=".json",
            delete=False,
        ) as partial_buffer:
            partial_buffer_path = partial_buffer.name

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
            "timeout": int(engine_timeout if engine_timeout is not None else client.timeout),
            "max_retries": int(max_retries if max_retries is not None else client.max_retries),
            "partial_buffer_path": partial_buffer_path,
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
            partial_results = _read_partial_results(partial_buffer_path)
            if partial_results:
                logger.warning(
                    "DDGS worker timeout after %.1fs for query=%r; returning %d partial result(s)",
                    worker_timeout, _query_preview(query), len(partial_results),
                )
                return partial_results
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
            if partial_buffer_path:
                with contextlib.suppress(Exception):
                    Path(partial_buffer_path).unlink()
                with contextlib.suppress(Exception):
                    Path(partial_buffer_path + ".tmp").unlink()

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

    # In-process fallback when subprocess worker is disabled or missing.
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
