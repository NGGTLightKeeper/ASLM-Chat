# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Source cache: SQLite + FTS5 local page cache for cache-first retrieval.

Refactored from legacy src/source_cache.py:
  - Removed all sys.path hacks and try/except import fallbacks
  - URL helpers (canonicalize_url, url_hash, content_hash) are now
    inlined directly — no cross-module path dependency
  - Public API is unchanged

Public API
----------
SourceCache    -- main class, owns the SQLite DB
CachedPage     -- dataclass for a cached page record
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger("core.cache.source_cache")


# ---------------------------------------------------------------------------
# URL helpers (inlined from legacy crawl_frontier to remove cross-deps)
# ---------------------------------------------------------------------------

from core.fetch.url_utils import _TRACKING_PARAMS


def canonicalize_url(url: str) -> str:
    """Normalize a URL: https, strip www., sort/filter query params."""
    try:
        p = urlparse(url.strip())
        scheme = (p.scheme or "https").lower()
        if scheme == "http":
            scheme = "https"
        netloc = p.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = p.path or "/"
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        qp = parse_qs(p.query, keep_blank_values=False)
        filtered = {k: v for k, v in qp.items() if k.lower() not in _TRACKING_PARAMS}
        sorted_q = urlencode(sorted(filtered.items()), doseq=True)
        return urlunparse((scheme, netloc, path, "", sorted_q, ""))
    except Exception:
        return url.strip()


def url_hash(url: str) -> str:
    return hashlib.sha256(canonicalize_url(url).encode()).hexdigest()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class CachedPage:
    """A cached page record."""

    url: str
    domain: str
    title: str
    clean_text: str
    raw_html: str
    fetched_at: float
    content_hash: str
    status: str          # "ok" | "error" | "antibot" | "timeout"
    char_count: int
    score: float = 0.0   # FTS5 BM25 score (only set by search_local)


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS pages (
    url_hash     TEXT PRIMARY KEY,
    url          TEXT NOT NULL,
    domain       TEXT NOT NULL,
    title        TEXT DEFAULT '',
    clean_text   TEXT DEFAULT '',
    raw_html     TEXT DEFAULT '',
    fetched_at   REAL NOT NULL,
    content_hash TEXT DEFAULT '',
    status       TEXT DEFAULT 'ok',
    char_count   INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_pages_domain     ON pages(domain);
CREATE INDEX IF NOT EXISTS idx_pages_fetched_at ON pages(fetched_at);
CREATE INDEX IF NOT EXISTS idx_pages_status     ON pages(status);

CREATE TABLE IF NOT EXISTS query_sources (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    query    TEXT NOT NULL,
    url_hash TEXT NOT NULL,
    rank     INTEGER DEFAULT 0,
    found_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_qs_query    ON query_sources(query);
CREATE INDEX IF NOT EXISTS idx_qs_url_hash ON query_sources(url_hash);

CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    url_hash UNINDEXED,
    title,
    clean_text,
    tokenize='porter unicode61'
);
"""


# ---------------------------------------------------------------------------
# SourceCache
# ---------------------------------------------------------------------------

class SourceCache:
    """SQLite + FTS5 source page cache."""

    def __init__(self, db_path: str, default_ttl: int = 86_400) -> None:
        self._db_path = db_path
        self._default_ttl = default_ttl
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    # -- Connection helpers --------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            for stmt in _SCHEMA_SQL.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)
            conn.commit()
        finally:
            conn.close()

    # -- Public API ----------------------------------------------------------

    def search_local(
        self,
        query: str,
        limit: int = 10,
        min_freshness_sec: int | None = None,
    ) -> list[CachedPage]:
        """Full-text search over cached pages using FTS5 + BM25.

        Returns pages ordered by relevance (title weighted 5x over body).
        Only returns pages with status='ok'.
        """
        if not query or not query.strip():
            return []

        max_age = min_freshness_sec or self._default_ttl
        cutoff = time.time() - max_age

        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT p.url, p.domain, p.title, p.clean_text, p.raw_html,
                       p.fetched_at, p.content_hash, p.status, p.char_count,
                       bm25(pages_fts, 5.0, 1.0) AS score
                FROM pages_fts
                JOIN pages p ON pages_fts.url_hash = p.url_hash
                WHERE pages_fts MATCH ?
                  AND p.status = 'ok'
                  AND p.fetched_at > ?
                ORDER BY score
                LIMIT ?
                """,
                (query, cutoff, limit),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("FTS5 search failed for %r: %s", query, exc)
            return []
        finally:
            conn.close()

        return [
            CachedPage(
                url=r["url"],
                domain=r["domain"],
                title=r["title"],
                clean_text=r["clean_text"],
                raw_html=r["raw_html"],
                fetched_at=r["fetched_at"],
                content_hash=r["content_hash"],
                status=r["status"],
                char_count=r["char_count"],
                score=r["score"],
            )
            for r in rows
        ]

    def cache_page(
        self,
        url: str,
        title: str,
        clean_text: str,
        raw_html: str = "",
        domain: str = "",
        status: str = "ok",
    ) -> None:
        """Insert or update a page in the cache."""
        if not domain:
            try:
                domain = urlparse(url).netloc.lower()
            except Exception:
                domain = ""

        uhash = url_hash(url)
        chash = content_hash(clean_text) if clean_text else ""
        now = time.time()

        conn = self._connect()
        try:
            # Wrap pages + FTS5 update in a single transaction so they
            # can never desync if the process crashes mid-write.
            with conn:
                conn.execute(
                    """
                    INSERT INTO pages (url_hash, url, domain, title, clean_text, raw_html,
                                       fetched_at, content_hash, status, char_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url_hash) DO UPDATE SET
                        title        = excluded.title,
                        clean_text   = excluded.clean_text,
                        raw_html     = excluded.raw_html,
                        fetched_at   = excluded.fetched_at,
                        content_hash = excluded.content_hash,
                        status       = excluded.status,
                        char_count   = excluded.char_count
                    """,
                    (uhash, canonicalize_url(url), domain, title, clean_text, raw_html,
                     now, chash, status, len(clean_text)),
                )
                # Explicitly maintain FTS5 index (UPSERT does not fire triggers).
                conn.execute("DELETE FROM pages_fts WHERE url_hash = ?", (uhash,))
                conn.execute(
                    "INSERT INTO pages_fts (url_hash, title, clean_text) VALUES (?, ?, ?)",
                    (uhash, title, clean_text),
                )
        finally:
            conn.close()

    def get_cached(self, url: str) -> Optional[CachedPage]:
        """Return a cached page by URL, or None."""
        uhash = url_hash(url)
        conn = self._connect()
        try:
            r = conn.execute(
                "SELECT * FROM pages WHERE url_hash = ?", (uhash,)
            ).fetchone()
        finally:
            conn.close()

        if not r:
            return None
        return CachedPage(
            url=r["url"],
            domain=r["domain"],
            title=r["title"],
            clean_text=r["clean_text"],
            raw_html=r["raw_html"],
            fetched_at=r["fetched_at"],
            content_hash=r["content_hash"],
            status=r["status"],
            char_count=r["char_count"],
        )

    def is_fresh(self, url: str, max_age_sec: int | None = None) -> bool:
        """Check whether a cached page exists and is still fresh."""
        uhash = url_hash(url)
        ttl = max_age_sec or self._default_ttl
        cutoff = time.time() - ttl

        conn = self._connect()
        try:
            r = conn.execute(
                "SELECT fetched_at FROM pages WHERE url_hash = ? AND status = 'ok'",
                (uhash,),
            ).fetchone()
        finally:
            conn.close()

        return r is not None and r["fetched_at"] > cutoff

    def record_query_source(self, query: str, url: str, rank: int) -> None:
        """Record which query discovered which URL.

        The query is stored in its normalized form so that semantically
        equivalent queries (different word order, stopwords removed) map to
        the same record.
        """
        from core.cache.query_normalizer import normalize_query_key
        uhash = url_hash(url)
        now = time.time()
        normalized = normalize_query_key(query)

        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO query_sources (query, url_hash, rank, found_at) VALUES (?, ?, ?, ?)",
                (normalized, uhash, rank, now),
            )
            conn.commit()
        finally:
            conn.close()

    def evict_stale(self, max_age_sec: int = 604_800) -> int:
        """Delete pages older than max_age_sec. Returns number of deleted rows."""
        cutoff = time.time() - max_age_sec

        conn = self._connect()
        try:
            stale_hashes = [
                r[0] for r in conn.execute(
                    "SELECT url_hash FROM pages WHERE fetched_at < ?", (cutoff,)
                ).fetchall()
            ]
            if stale_hashes:
                placeholders = ",".join("?" * len(stale_hashes))
                conn.execute(
                    f"DELETE FROM pages_fts WHERE url_hash IN ({placeholders})",
                    stale_hashes,
                )
            cur = conn.execute("DELETE FROM pages WHERE fetched_at < ?", (cutoff,))
            conn.execute(
                "DELETE FROM query_sources WHERE url_hash NOT IN (SELECT url_hash FROM pages)"
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def page_count(self) -> int:
        """Return total number of cached pages."""
        conn = self._connect()
        try:
            r = conn.execute("SELECT COUNT(*) AS cnt FROM pages").fetchone()
            return r["cnt"] if r else 0
        finally:
            conn.close()

    def cache_stats(self) -> dict:
        """Return basic cache statistics."""
        conn = self._connect()
        try:
            total = conn.execute("SELECT COUNT(*) AS c FROM pages").fetchone()["c"]
            ok = conn.execute("SELECT COUNT(*) AS c FROM pages WHERE status='ok'").fetchone()["c"]
            queries = conn.execute("SELECT COUNT(DISTINCT query) AS c FROM query_sources").fetchone()["c"]
            return {"total_pages": total, "ok_pages": ok, "unique_queries": queries}
        finally:
            conn.close()
