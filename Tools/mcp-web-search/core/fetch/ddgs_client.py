# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
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
from threading import Lock
from typing import Optional

from core.models.search import SearchResult
from core.fetch.thread_pool import io_pool as _io_pool
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
    from core.ddgs import DDGS
    from core.ddgs.exceptions import DDGSException, RatelimitException, TimeoutException
    _DDGS_AVAILABLE = True
    _EXCEPTION_CLASSES = (RatelimitException, TimeoutException, DDGSException)
except ImportError:
    _DDGS_AVAILABLE = False
    _EXCEPTION_CLASSES = (Exception,)

_RETRYABLE_ERRORS = ("ssl", "eof", "connect", "connection", "timeout", "reset", "broken pipe")
_HARD_FAILURE_ERRORS = ("403", "forbidden")
DEFAULT_REGION = "us-en"
_OPERATOR_TOKEN_RE = re.compile(r"(?<!\S)(?:-?site:[^\s]+|inurl:[^\s]+|intitle:[^\s]+|filetype:[^\s]+|(?:OR|\|))(?=\s|$)", re.IGNORECASE)
_LEXICAL_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]{2,}|[А-Яа-яЁё0-9_\-]{2,}")

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


BACKEND_FALLBACK = ["startpage", "mojeek", "brave", "yandex"]
BACKEND_SITE_QUERY = ["yandex", "yahoo", "startpage"]


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
        region: str = DEFAULT_REGION,
        timelimit: Optional[str] = None,
        cache_ttl: Optional[int] = None,
        language: str | None = None,
        query_types: list[str] | None = None,
        class_weights: dict[str, float] | None = None,
        max_attempts: int = 1,
        routing_profile: str = "stability",
    ) -> list[dict]:
        if not _DDGS_AVAILABLE:
            logger.error("vendored core.ddgs search provider is unavailable")
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
            language=language or "",
            query_types=query_types or [],
            class_weights=class_weights or {},
            max_attempts=max_attempts,
            routing_profile=routing_profile,
        )
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        attempts = 1 if backend in {"auto", "all"} else self.max_retries
        for attempt in range(attempts):
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
                    "language": language,
                    "query_types": query_types,
                    "class_weights": class_weights,
                    "max_attempts": max_attempts,
                    "routing_profile": routing_profile,
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
                logger.log(log_level, "DDGS attempt %s/%s: %s", attempt + 1, attempts, error)
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
                    logger.warning("DDGS attempt %s/%s: %s", attempt + 1, attempts, error)
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
        region: str = DEFAULT_REGION,
        timelimit: Optional[str] = None,
        cache_ttl: Optional[int] = None,
        language: str | None = None,
        query_types: list[str] | None = None,
        class_weights: dict[str, float] | None = None,
        max_attempts: int = 1,
        routing_profile: str = "stability",
    ) -> list[SearchResult]:
        raw = self.search_sync(
            query=query,
            max_results=max_results,
            backend=backend,
            region=region,
            timelimit=timelimit,
            cache_ttl=cache_ttl,
            language=language,
            query_types=query_types,
            class_weights=class_weights,
            max_attempts=max_attempts,
            routing_profile=routing_profile,
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
                    engine=f"ddgs:{item.get('_engine') or backend}",
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
        class_weights: Optional[dict[str, float]] = None,
        lang: str = "en",
        timelimit: Optional[str] = None,
        hedge_count: int = 2,
        routing_profile: str = "stability",
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

        # core.ddgs owns language routing, provider-family diversity, health,
        # suspension, and latency-aware sequential attempts.
        ttl = _effective_ttl(_qtypes, timelimit)
        result = self.search_to_results(
            query,
            max_results,
            backend="auto",
            region=DEFAULT_REGION,
            timelimit=timelimit,
            cache_ttl=ttl,
            language=lang,
            query_types=_qtypes,
            class_weights=class_weights,
            max_attempts=max(1, hedge_count),
            routing_profile=routing_profile,
        )
        if result:
            _write_partial_results(partial_buffer_path, result)
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
    class_weights: Optional[dict[str, float]] = None,
    lang: str = "en",
    timelimit: Optional[str] = None,
    use_subprocess: Optional[bool] = None,
    worker_timeout: Optional[float] = None,
    hedge_count: int = 2,
    routing_profile: str = "stability",
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
            "class_weights": class_weights,
            "lang": lang,
            "timelimit": timelimit,
            "hedge_count": hedge_count,
            "routing_profile": routing_profile,
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
            class_weights=class_weights,
            lang=lang,
            timelimit=timelimit,
            hedge_count=hedge_count,
            routing_profile=routing_profile,
        )

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_io_pool, _sync)
