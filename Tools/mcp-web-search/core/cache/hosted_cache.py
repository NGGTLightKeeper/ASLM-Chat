# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from core.models.search import SearchResult
from core.cache.query_normalizer import normalize_exact_query_key, normalize_query_key

logger = logging.getLogger("core.cache.hosted_cache")

# TTL seconds per query classification (mirrors ddgs_client policy).
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
_DEFAULT_TTL:  int = 1_800    # 30 min fallback
NEGATIVE_TTL:  int = 300      # 5 min — empty result set


# Return cache TTL in seconds for the given query classification.
def query_ttl(query_type: str) -> int:
    return _QUERY_TTL.get(query_type, _DEFAULT_TTL)


# Serialize a SearchResult for SQLite JSON storage.
def _result_to_dict(r: SearchResult) -> dict:
    return {
        "url":              r.url,
        "title":            r.title,
        "snippet":          r.snippet,
        "engine":           r.engine,
        "published_date":   r.published_date,
        "pdf_url":          r.pdf_url,
        "provider_content": r.provider_content,
    }


# Deserialize a dict from hosted_cache back into SearchResult.
def _dict_to_result(d: dict) -> SearchResult:
    return SearchResult(
        url=d.get("url", ""),
        title=d.get("title", ""),
        snippet=d.get("snippet", ""),
        engine=d.get("engine", ""),
        published_date=d.get("published_date", ""),
        pdf_url=d.get("pdf_url", ""),
        provider_content=d.get("provider_content", ""),
    )


# SQLite-backed cache for hosted provider search results (key excludes API key).
class HostedSearchCache:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._write_lock = threading.Lock()
        self._local = threading.local()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # Return a per-thread persistent SQLite connection.
    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    # Create hosted_cache table and indexes if needed.
    def _init_db(self) -> None:
        with self._write_lock:
            conn = self._get_conn()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hosted_cache (
                    key      TEXT    PRIMARY KEY,
                    provider TEXT    NOT NULL,
                    data     TEXT    NOT NULL,
                    ts       REAL    NOT NULL,
                    ttl      INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_hosted_cache_provider "
                "ON hosted_cache(provider)"
            )
            conn.commit()

    # Deterministic cache key — independent of which API key was used.
    @staticmethod
    def make_key(provider: str, query: str, timelimit: Optional[str]) -> str:
        normalized = normalize_query_key(query)
        exact = normalize_exact_query_key(query)
        raw = f"{provider}:{exact}|{normalized}|{timelimit or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()

    # Return cached results or None if missing or expired.
    def get(
        self,
        provider: str,
        query: str,
        timelimit: Optional[str] = None,
    ) -> Optional[list[SearchResult]]:
        key = self.make_key(provider, query, timelimit)
        row = self._get_conn().execute(
            "SELECT data, ts, ttl FROM hosted_cache WHERE key = ?",
            (key,),
        ).fetchone()

        if row is None:
            return None
        age = time.time() - row["ts"]
        if age > row["ttl"]:
            return None

        try:
            items = json.loads(row["data"])
            return [_dict_to_result(d) for d in items]
        except Exception as exc:
            logger.warning("[hosted_cache] deserialize error for key %s: %s", key[:12], exc)
            return None

    # Store results; empty list uses NEGATIVE_TTL.
    def set(
        self,
        provider: str,
        query: str,
        results: list[SearchResult],
        *,
        timelimit: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> None:
        effective_ttl = ttl if ttl is not None else (NEGATIVE_TTL if not results else _DEFAULT_TTL)
        key = self.make_key(provider, query, timelimit)
        data = json.dumps([_result_to_dict(r) for r in results], ensure_ascii=False)

        with self._write_lock:
            try:
                conn = self._get_conn()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO hosted_cache (key, provider, data, ts, ttl)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (key, provider, data, time.time(), effective_ttl),
                )
                conn.commit()
            except Exception as exc:
                logger.warning("[hosted_cache] write error: %s", exc)

    # Delete expired entries; returns number of deleted rows.
    def evict_expired(self) -> int:
        with self._write_lock:
            try:
                conn = self._get_conn()
                result = conn.execute(
                    "DELETE FROM hosted_cache WHERE (? - ts) > ttl",
                    (time.time(),),
                )
                conn.commit()
                deleted = result.rowcount
            except Exception as exc:
                logger.warning("[hosted_cache] evict_expired error: %s", exc)
                deleted = 0
        if deleted:
            logger.info("hosted_cache: evicted %d expired entries", deleted)
        return deleted

    # Return basic cache statistics, optionally filtered by provider.
    def stats(self, provider: Optional[str] = None) -> dict:
        conn = self._get_conn()
        now = time.time()
        if provider:
            row = conn.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN (? - ts) <= ttl THEN 1 ELSE 0 END) as fresh "
                "FROM hosted_cache WHERE provider = ?",
                (now, provider),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN (? - ts) <= ttl THEN 1 ELSE 0 END) as fresh "
                "FROM hosted_cache",
                (now,),
            ).fetchone()
        return {
            "total": row["total"] or 0,
            "fresh": row["fresh"] or 0,
            "expired": (row["total"] or 0) - (row["fresh"] or 0),
        }


_CACHE_PATH = Path(__file__).resolve().parents[2] / "_cache" / "hosted_cache.db"

_singleton: Optional[HostedSearchCache] = None
_singleton_lock = threading.Lock()


# Return the lazily initialised global HostedSearchCache.
def get_hosted_cache() -> HostedSearchCache:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = HostedSearchCache(str(_CACHE_PATH))
    return _singleton
