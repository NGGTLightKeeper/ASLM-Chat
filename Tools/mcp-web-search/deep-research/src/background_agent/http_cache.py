# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import hashlib
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

logger = logging.getLogger("background_agent.http_cache")


# Cached response models.
# Cached HTTP response record.
@dataclass
class CachedResponse:
    """Cached HTTP response payload and metadata."""

    url: str
    status: int
    html: str
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    content_type: Optional[str] = None
    cached_at: float = 0.0
    size_bytes: int = 0


# HTTP cache implementation.
# SQLite-backed HTTP cache.
class HTTPCache:
    # Configure cache storage settings.
    def __init__(
        self,
        db_path: str = ":memory:",
        default_max_age: int = 3600,
    ):
        self._db_path = db_path
        self._default_max_age = default_max_age
        self._db_uri: Optional[str] = None
        self._keeper_conn: Optional[sqlite3.Connection] = None
        if self._db_path == ":memory:":
            self._db_uri = f"file:http_cache_{uuid.uuid4().hex}?mode=memory&cache=shared"
        self._init_db()
        self._stats = {"hits": 0, "misses": 0, "conditionals_304": 0, "stored": 0}

    # Open one database connection.
    def _connect(self) -> sqlite3.Connection:
        """Open a database connection for the cache."""

        if self._db_uri:
            return sqlite3.connect(self._db_uri, uri=True)
        return sqlite3.connect(self._db_path)

    # Create the cache schema.
    def _init_db(self):
        """Create the cache schema and keep memory-backed databases alive."""

        conn = self._connect()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS http_cache (
                url_hash      TEXT PRIMARY KEY,
                url           TEXT NOT NULL,
                status        INTEGER,
                html          TEXT,
                etag          TEXT,
                last_modified TEXT,
                content_type  TEXT,
                cached_at     REAL,
                size_bytes    INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_cached_at ON http_cache(cached_at)
            """
        )
        conn.commit()
        if self._db_uri:
            self._keeper_conn = conn
        else:
            conn.close()
        logger.info(f"HTTPCache initialized: {self._db_path if not self._db_uri else self._db_uri}")

    # Hash a canonical URL for storage.
    def _url_hash(self, url: str) -> str:
        """Hash the canonical URL used as the cache key."""

        from .crawl_frontier import canonicalize_url

        canonical = canonicalize_url(url)
        return hashlib.sha256(canonical.encode()).hexdigest()

    # Return conditional request headers for a URL.
    def get_conditional_headers(self, url: str) -> Dict[str, str]:
        """Return ETag and Last-Modified headers for conditional requests."""

        url_key = self._url_hash(url)
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT etag, last_modified FROM http_cache WHERE url_hash = ?",
                (url_key,),
            ).fetchone()
            if not row:
                return {}
            headers = {}
            if row[0]:
                headers["If-None-Match"] = row[0]
            if row[1]:
                headers["If-Modified-Since"] = row[1]
            return headers
        finally:
            conn.close()

    # Store one fetched response.
    def store(
        self,
        url: str,
        html: str,
        status: int = 200,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        content_type: Optional[str] = None,
    ):
        """Store a fetched page in the cache."""

        url_key = self._url_hash(url)
        size_bytes = len(html.encode("utf-8", errors="replace"))
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO http_cache
                (url_hash, url, status, html, etag, last_modified, content_type, cached_at, size_bytes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    url_key,
                    url,
                    status,
                    html,
                    etag,
                    last_modified,
                    content_type,
                    time.time(),
                    size_bytes,
                ),
            )
            conn.commit()
            self._stats["stored"] += 1
            logger.debug(f"HTTPCache stored: {url[:60]} ({size_bytes} bytes)")
        finally:
            conn.close()

    # Load one cached response.
    def get_cached(self, url: str) -> Optional[CachedResponse]:
        """Return the cached response for a URL, if present."""

        url_key = self._url_hash(url)
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT url, status, html, etag, last_modified, content_type, cached_at, size_bytes
                FROM http_cache WHERE url_hash = ?
                """,
                (url_key,),
            ).fetchone()
            if not row:
                self._stats["misses"] += 1
                return None
            self._stats["hits"] += 1
            return CachedResponse(
                url=row[0],
                status=row[1],
                html=row[2],
                etag=row[3],
                last_modified=row[4],
                content_type=row[5],
                cached_at=row[6],
                size_bytes=row[7],
            )
        finally:
            conn.close()

    # Check whether a cached response is still fresh.
    def is_fresh(self, url: str, max_age_sec: Optional[int] = None) -> bool:
        """Return whether the cached entry is still fresh."""

        max_age = max_age_sec or self._default_max_age
        url_key = self._url_hash(url)
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT cached_at FROM http_cache WHERE url_hash = ?",
                (url_key,),
            ).fetchone()
            if not row:
                return False
            return (time.time() - row[0]) < max_age
        finally:
            conn.close()

    # Refresh a cached row after a 304 response.
    def mark_304(self, url: str):
        """Refresh the timestamp after a 304 Not Modified response."""

        url_key = self._url_hash(url)
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE http_cache SET cached_at = ? WHERE url_hash = ?",
                (time.time(), url_key),
            )
            conn.commit()
            self._stats["conditionals_304"] += 1
        finally:
            conn.close()

    # Delete cache rows older than the cutoff.
    def evict_old(self, max_age_sec: int = 86400) -> int:
        """Delete cache rows older than the requested age."""

        cutoff = time.time() - max_age_sec
        conn = self._connect()
        try:
            conn.execute("DELETE FROM http_cache WHERE cached_at < ?", (cutoff,))
            deleted = conn.total_changes
            conn.commit()
            return deleted
        finally:
            conn.close()

    # Return cache row count and size.
    def cache_size(self) -> Tuple[int, int]:
        """Return cache row count and total payload size in bytes."""

        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(size_bytes), 0) FROM http_cache"
            ).fetchone()
            return row[0], row[1]
        finally:
            conn.close()

    # Return cache usage statistics.
    @property
    def stats(self) -> Dict[str, int]:
        """Return cache usage counters."""

        return dict(self._stats)
