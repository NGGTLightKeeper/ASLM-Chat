# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import hashlib
import json
import logging
import random
import sqlite3
import time
from dataclasses import dataclass
from threading import Lock
from typing import Optional

logger = logging.getLogger("ddgs_client")

try:
    from config import DDGS_MAX_RETRIES, DDGS_REQUEST_DELAY, DDGS_TIMEOUT
except ImportError:
    DDGS_REQUEST_DELAY = (0.15, 0.6)
    DDGS_TIMEOUT = 5
    DDGS_MAX_RETRIES = 1


# Compatibility imports.
try:
    from ddgs import DDGS
    from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException

    _DDGS_AVAILABLE = True
    _EXCEPTION_CLASSES = (RatelimitException, TimeoutException, DDGSException)
except ImportError:
    try:
        from duckduckgo_search import DDGS

        _DDGS_AVAILABLE = True
        _EXCEPTION_CLASSES = (Exception,)
    except ImportError:
        _DDGS_AVAILABLE = False
        _EXCEPTION_CLASSES = (Exception,)

_RETRYABLE_ERRORS = ("ssl", "eof", "connect", "connection", "timeout", "reset", "broken pipe")

try:
    from src.models import SearchResult
except ImportError:

    # Fallback result model.
    # Standalone search-result model.
    @dataclass
    class SearchResult:
        """Fallback search-result model for standalone imports."""

        url: str = ""
        title: str = ""
        snippet: str = ""
        engine: str = ""
        score: float = 0.0
        trust_tier: str = "?"


# Backend configuration.
BACKEND_PRESETS = {
    "technical": "google,brave",
    "academic": "google,brave",
    "general": "auto",
    "journalistic": "auto",
    "finance": "google,yahoo",
    "medical": "google,brave",
    "ru": "yandex,google",
}
BACKEND_FALLBACK = ["google,brave", "mojeek", "auto"]
BACKEND_SITE_QUERY = ["yandex,yahoo", "auto"]


# DDGS client.
class DDGSClient:
    """Wrap DDGS with retry, cache, and optional proxy handling."""

    # Construction helpers.
    def __init__(
        self,
        proxies: Optional[list[str]] = None,
        cache_db: Optional[str] = None,
        cache_ttl: int = 3600,
        proxy_cooldown: int = 3600,
        request_delay: tuple[float, float] = (1.0, 3.0),
        timeout: int = 15,
        max_retries: int = 3,
    ):
        """Store runtime settings and initialize optional cache state."""

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


    # Proxy helpers.
    def _get_proxy(self) -> Optional[str]:
        """Return one currently available proxy or None."""

        if not self.proxies:
            return None

        with self._proxy_lock:
            now = time.time()
            available = [
                proxy
                for proxy in self.proxies
                if proxy not in self._blocked_proxies
                or now - self._blocked_proxies[proxy] > self._proxy_cooldown
            ]
            return random.choice(available) if available else None

    # Proxy helpers.
    def _block_proxy(self, proxy: str):
        """Temporarily mark a proxy as unhealthy after rate limiting."""

        with self._proxy_lock:
            self._blocked_proxies[proxy] = time.time()
            logger.warning("Proxy blocked: %s...", proxy[:30])


    # Cache helpers.
    def _init_cache(self):
        """Create the on-disk DDGS cache table when caching is enabled."""

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

    # Cache helpers.
    def _cache_key(self, query: str, **kwargs) -> str:
        """Build a stable cache key for a search request."""

        raw = f"{query.strip().lower()}|{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    # Cache helpers.
    def _cache_get(self, key: str) -> Optional[list]:
        """Return cached rows when the entry is still fresh."""

        if not self._cache_db:
            return None

        try:
            with sqlite3.connect(self._cache_db) as conn:
                row = conn.execute(
                    "SELECT data, ts, ttl FROM ddgs_cache WHERE key = ?",
                    (key,),
                ).fetchone()
                if row and time.time() - row[1] < row[2]:
                    return json.loads(row[0])
        except Exception:
            pass

        return None

    # Cache helpers.
    def _cache_set(self, key: str, data: list, ttl: Optional[int] = None):
        """Persist search rows in the local cache."""

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


    # Search helpers.
    @staticmethod
    # Clean a query before sending it to DDGS.
    def _sanitize_query(query: str) -> str:
        """Trim and compact a query before sending it to DDGS."""

        query = query.strip()
        query = " ".join(query.split())
        if len(query) > 100:
            query = " ".join(query.split()[:10])
        if len(query) > 120:
            query = query[:120]

        return query

    # Search helpers.
    def search_sync(
        self,
        query: str,
        max_results: int = 10,
        backend: str = "auto",
        region: str = "wt-wt",
        timelimit: Optional[str] = None,
    ) -> list[dict]:
        """Run one synchronous DDGS search with retries and caching."""

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
                # Spread requests a little even on the first attempt, then back off harder.
                if attempt > 0:
                    delay = min(2 * attempt + random.uniform(0, 0.5), 4)
                    time.sleep(delay)
                else:
                    time.sleep(random.uniform(*self.request_delay))

                ddgs = DDGS(proxy=proxy, timeout=self.timeout)
                ddgs_kwargs = {
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
                if results:
                    self._cache_set(cache_key, results)
                return results
            except _EXCEPTION_CLASSES as error:
                message = str(error)
                log_level = logging.DEBUG if "No results found" in message else logging.WARNING
                logger.log(log_level, "DDGS attempt %s/%s failed: %s", attempt + 1, self.max_retries, error)
                if proxy and "ratelimit" in message.lower():
                    self._block_proxy(proxy)
            except Exception as error:
                message = str(error).lower()
                if any(keyword in message for keyword in _RETRYABLE_ERRORS):
                    logger.warning("DDGS attempt %s/%s failed: %s", attempt + 1, self.max_retries, error)
                else:
                    logger.debug("DDGS unexpected error: %s", error)
                    break

        return []

    # Search helpers.
    def search_to_results(
        self,
        query: str,
        max_results: int = 10,
        backend: str = "auto",
        region: str = "wt-wt",
        timelimit: Optional[str] = None,
    ) -> list[SearchResult]:
        """Convert raw DDGS rows into SearchResult objects."""

        raw = self.search_sync(
            query=query,
            max_results=max_results,
            backend=backend,
            region=region,
            timelimit=timelimit,
        )

        results = []
        for item in raw:
            url = item.get("href") or item.get("url") or ""
            if not url:
                continue

            results.append(
                SearchResult(
                    url=url,
                    title=item.get("title", ""),
                    snippet=item.get("body", "") or item.get("snippet", ""),
                    engine=f"ddgs:{backend}",
                )
            )

        return results

    # Search helpers.
    def search_with_fallback(
        self,
        query: str,
        max_results: int = 10,
        query_type: str = "general",
        lang: str = "en",
        timelimit: Optional[str] = None,
    ) -> list[SearchResult]:
        """Try multiple backends until one returns search results."""

        if query.lstrip().lower().startswith("site:"):
            backends_to_try = list(BACKEND_SITE_QUERY)
        elif lang == "ru":
            backends_to_try = ["yandex,google", "yandex,yahoo", "auto"]
        else:
            initial = BACKEND_PRESETS.get(query_type, "auto")
            backends_to_try = [initial] + [backend for backend in BACKEND_FALLBACK if backend != initial]

        for backend in backends_to_try:
            results = self.search_to_results(
                query=query,
                max_results=max_results,
                backend=backend,
                timelimit=timelimit,
            )
            if results:
                return results

        return []


# Async interface.
_client: Optional[DDGSClient] = None


# Async interface.
def get_ddgs_client(
    proxies: Optional[list[str]] = None,
    cache_db: Optional[str] = None,
) -> DDGSClient:
    """Return the lazily initialized global DDGS client."""

    global _client

    if _client is None:
        _client = DDGSClient(
            proxies=proxies or [],
            cache_db=cache_db,
            cache_ttl=3600,
            request_delay=DDGS_REQUEST_DELAY,
            timeout=DDGS_TIMEOUT,
            max_retries=DDGS_MAX_RETRIES,
        )

    return _client

# Async interface.
async def async_ddgs_search(
    query: str,
    max_results: int = 10,
    query_type: str = "general",
    lang: str = "en",
    timelimit: Optional[str] = None,
) -> list[SearchResult]:
    """Run DDGS search in an executor for asyncio callers."""

    client = get_ddgs_client()

    # Keep the public API async while reusing the sync implementation.
    def _sync():
        return client.search_with_fallback(
            query=query,
            max_results=max_results,
            query_type=query_type,
            lang=lang,
            timelimit=timelimit,
        )

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync)


# Local smoke-test entry point.
if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]) or "GLiNER NER model architecture"
    print(f"Searching: {query}")

    client = DDGSClient(cache_db="test_cache.db", request_delay=(0.5, 1.5))
    results = client.search_with_fallback(query, max_results=5, query_type="technical")

    print(f"Found {len(results)} results:")
    for index, result in enumerate(results, 1):
        print(f"  {index}. [{result.engine}] {result.title[:70]}")
        print(f"     {result.url}")
        print(f"     {result.snippet[:100]}...")
        print()
