# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time

from .known_domains import domain_of, get_override
from .models import FetchAttempt, ProfileHint

logger = logging.getLogger("core.profiles.runtime")

# Observations older than this are ignored when recommending a method, so a site that
# changed its protection no longer pins read_page to a stale strategy.
_TTL_SECONDS = 14 * 86_400
# Recency half-life: a fortnight-old success counts half as much as a fresh one.
_HALFLIFE_SECONDS = 7 * 86_400
# Below this many observations a recommendation is low-confidence (still usable as a hint).
_MIN_OBS_FOR_CONFIDENCE = 2
# A working method whose mean wall-clock fetch exceeds this is flagged avoid for fast paths.
_AVOID_FETCH_MS = 12_000.0
# A method that succeeds less than half the time is treated as unreliable.
_MIN_SUCCESS_RATE = 0.5

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS domain_methods (
    domain            TEXT NOT NULL,
    method            TEXT NOT NULL,
    obs               INTEGER NOT NULL DEFAULT 0,
    success           INTEGER NOT NULL DEFAULT 0,
    blocked           INTEGER NOT NULL DEFAULT 0,
    timeout           INTEGER NOT NULL DEFAULT 0,
    empty             INTEGER NOT NULL DEFAULT 0,
    sum_fetch_ms      REAL NOT NULL DEFAULT 0,
    sum_parse_ms      REAL NOT NULL DEFAULT 0,
    sum_quality       REAL NOT NULL DEFAULT 0,
    last_user_agent   TEXT NOT NULL DEFAULT '',
    last_seen         REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (domain, method)
);

CREATE INDEX IF NOT EXISTS idx_dm_domain ON domain_methods(domain);
"""


# Learns, per (domain, fetch-method), how reliable and how fast each approach is, so
# read_page can pick a known-good method up front instead of probing a fallback chain.
class RuntimeDomainProfiles:

    # Open the SQLite store and apply the schema.
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._local = threading.local()
        self._write_lock = threading.Lock()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    # Return a per-thread persistent SQLite connection.
    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return conn

    # Apply schema DDL on first open.
    def _init_db(self) -> None:
        conn = self._get_conn()
        for stmt in _SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()

    # Record one fetch attempt against a domain, updating rolling per-method statistics.
    def record(self, url_or_domain: str, attempt: FetchAttempt) -> None:
        domain = domain_of(url_or_domain)
        if not domain or not attempt.method:
            return
        now = time.time()
        try:
            with self._write_lock:
                conn = self._get_conn()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO domain_methods (
                            domain, method, obs, success, blocked, timeout, empty,
                            sum_fetch_ms, sum_parse_ms, sum_quality, last_user_agent, last_seen
                        )
                        VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(domain, method) DO UPDATE SET
                            obs             = obs + 1,
                            success         = success + excluded.success,
                            blocked         = blocked + excluded.blocked,
                            timeout         = timeout + excluded.timeout,
                            empty           = empty + excluded.empty,
                            sum_fetch_ms    = sum_fetch_ms + excluded.sum_fetch_ms,
                            sum_parse_ms    = sum_parse_ms + excluded.sum_parse_ms,
                            sum_quality     = sum_quality + excluded.sum_quality,
                            last_user_agent = excluded.last_user_agent,
                            last_seen       = excluded.last_seen
                        """,
                        (
                            domain,
                            attempt.method,
                            1 if attempt.success else 0,
                            1 if attempt.blocked else 0,
                            1 if attempt.timed_out else 0,
                            1 if attempt.empty else 0,
                            float(attempt.fetch_ms),
                            float(attempt.parse_ms),
                            float(attempt.quality),
                            attempt.user_agent or "",
                            now,
                        ),
                    )
        except sqlite3.DatabaseError as exc:
            logger.warning("runtime_profiles: record failed domain=%r: %s", domain, exc)

    # Recommend the best learned fetch method for a domain, or None when unknown.
    # A hard override from known_domains wins while runtime confidence is still low.
    def best_method(self, url_or_domain: str) -> ProfileHint | None:
        domain = domain_of(url_or_domain)
        if not domain:
            return None

        override = get_override(domain)

        try:
            rows = self._get_conn().execute(
                "SELECT * FROM domain_methods WHERE domain = ?", (domain,)
            ).fetchall()
        except sqlite3.DatabaseError as exc:
            logger.warning("runtime_profiles: lookup failed domain=%r: %s", domain, exc)
            rows = []

        now = time.time()
        best: ProfileHint | None = None
        best_rank: tuple[float, float] = (-1.0, 0.0)
        for row in rows:
            obs = int(row["obs"] or 0)
            success = int(row["success"] or 0)
            last_seen = float(row["last_seen"] or 0.0)
            if obs <= 0 or success <= 0:
                continue
            age = now - last_seen
            if age > _TTL_SECONDS:
                continue
            decay = 0.5 ** (age / _HALFLIFE_SECONDS)
            success_rate = success / obs
            avg_fetch_ms = float(row["sum_fetch_ms"] or 0.0) / obs
            avg_quality = float(row["sum_quality"] or 0.0) / obs
            confidence = success_rate * decay * min(1.0, obs / _MIN_OBS_FOR_CONFIDENCE)
            # Rank by reliability first, then prefer the cheaper method.
            rank = (round(success_rate * decay, 4), -avg_fetch_ms)
            if rank > best_rank:
                best_rank = rank
                best = ProfileHint(
                    method=str(row["method"]),
                    user_agent=str(row["last_user_agent"] or ""),
                    expected_fetch_ms=avg_fetch_ms,
                    expected_quality=avg_quality,
                    confidence=round(confidence, 4),
                    avoid=success_rate < _MIN_SUCCESS_RATE or avg_fetch_ms > _AVOID_FETCH_MS,
                )

        # Hard override takes precedence until runtime data is both present and confident.
        if override and override.required_method:
            if best is None or best.confidence < 0.5 or best.method != override.required_method:
                return ProfileHint(
                    method=override.required_method,
                    confidence=1.0,
                    avoid=False,
                )
        return best


_store: RuntimeDomainProfiles | None = None

# Runtime DB lives beside the page cache under the server root's _cache/ directory.
from pathlib import Path  # noqa: E402

_DB_PATH = Path(__file__).resolve().parents[2] / "_cache" / "domain_runtime.db"


# Shared RuntimeDomainProfiles singleton.
def get_runtime_profiles() -> RuntimeDomainProfiles:
    global _store
    if _store is None:
        _store = RuntimeDomainProfiles(str(_DB_PATH))
    return _store
