# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import math
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

try:
    from .config import DOMAIN_PERF_DB
except Exception:  # pragma: no cover - fallback for direct imports
    try:
        from config import DOMAIN_PERF_DB  # type: ignore
    except Exception:
        DOMAIN_PERF_DB = os.path.join(os.getcwd(), "_cache", "domain_performance.db")


# Domain performance snapshots.
# Aggregated domain performance snapshot.
@dataclass
class DomainPerfStats:
    """Store aggregated extraction statistics for one domain."""

    domain: str
    attempts: int
    successes: int
    total_chars: int
    last_ts: float

    # Derived metrics.
    # Return the stored success ratio.
    @property
    def success_rate(self) -> float:
        """Return the raw success ratio for the stored attempts."""

        if self.attempts <= 0:
            return 0.0

        return self.successes / float(self.attempts)


# Domain performance storage.
class DomainPerformanceStore:
    """Track per-domain extraction reliability with SQLite and a memory fallback."""

    # Construction helpers.
    def __init__(self, db_path: Optional[str] = None):
        """Initialize persistence and create the schema when possible."""

        self.db_path = db_path or DOMAIN_PERF_DB
        self._lock = threading.RLock()
        self._sqlite_ok = True
        self._memory: dict[tuple[str, str], DomainPerfStats] = {}
        self._init_db()

    # SQLite helpers.
    def _init_db(self) -> None:
        """Create the SQLite schema unless the store runs purely in memory."""

        if self.db_path != ":memory:":
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS domain_perf (
                        domain TEXT NOT NULL,
                        method TEXT NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        successes INTEGER NOT NULL DEFAULT 0,
                        total_chars INTEGER NOT NULL DEFAULT 0,
                        last_ts REAL NOT NULL DEFAULT 0,
                        PRIMARY KEY (domain, method)
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_domain_perf_domain ON domain_perf(domain)"
                )
        except Exception:
            self._sqlite_ok = False

    # Normalization helpers.
    @staticmethod
    # Extract a normalized domain from a URL or host.
    def _extract_domain(domain_or_url: str) -> str:
        """Normalize a domain or URL into a bare lowercase host."""

        value = (domain_or_url or "").strip().lower()
        if not value:
            return ""
        if "://" in value:
            value = urlparse(value).netloc.lower()
        if value.startswith("www."):
            value = value[4:]

        return value

    # Normalization helpers.
    @staticmethod
    # Normalize a method name for storage.
    def _normalize_method(method: Optional[str]) -> str:
        """Return a stable lowercase method name for storage."""

        normalized = (method or "").strip().lower()
        return normalized or "unknown"


    # Memory fallback helpers.
    def _memory_upsert(self, domain: str, method: str, success: bool, char_count: int, ts: float) -> None:
        """Update the in-memory fallback store for a single observation."""

        key = (domain, method)
        current = self._memory.get(key)
        if current is None:
            current = DomainPerfStats(domain=domain, attempts=0, successes=0, total_chars=0, last_ts=0.0)
            self._memory[key] = current

        current.attempts += 1
        if success:
            current.successes += 1
        current.total_chars += max(0, int(char_count))
        current.last_ts = max(current.last_ts, ts)

    # Memory fallback helpers.
    def _memory_aggregate(self, domain: str, method: Optional[str] = None) -> DomainPerfStats:
        """Aggregate all matching in-memory rows into one stats object."""

        attempts = 0
        successes = 0
        total_chars = 0
        last_ts = 0.0
        normalized = self._normalize_method(method) if method else None

        for (current_domain, current_method), stats in self._memory.items():
            if current_domain != domain:
                continue
            if normalized and current_method != normalized:
                continue

            attempts += stats.attempts
            successes += stats.successes
            total_chars += stats.total_chars
            last_ts = max(last_ts, stats.last_ts)

        return DomainPerfStats(
            domain=domain,
            attempts=attempts,
            successes=successes,
            total_chars=total_chars,
            last_ts=last_ts,
        )


    # Recording helpers.
    def record_attempt(
        self,
        domain_or_url: str,
        method: Optional[str],
        success: bool,
        char_count: int = 0,
        ts: Optional[float] = None,
    ) -> None:
        """Record one extraction attempt for the given domain and method."""

        domain = self._extract_domain(domain_or_url)
        if not domain:
            return

        normalized_method = self._normalize_method(method)
        now_ts = float(ts if ts is not None else time.time())
        chars = max(0, int(char_count or 0))

        with self._lock:
            if self._sqlite_ok:
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        conn.execute(
                            """
                            INSERT INTO domain_perf (domain, method, attempts, successes, total_chars, last_ts)
                            VALUES (?, ?, 1, ?, ?, ?)
                            ON CONFLICT(domain, method) DO UPDATE SET
                                attempts = attempts + 1,
                                successes = successes + excluded.successes,
                                total_chars = total_chars + excluded.total_chars,
                                last_ts = MAX(last_ts, excluded.last_ts)
                            """,
                            (domain, normalized_method, 1 if success else 0, chars, now_ts),
                        )
                    return
                except Exception:
                    self._sqlite_ok = False

            self._memory_upsert(domain, normalized_method, success, chars, now_ts)


    # Lookup helpers.
    def _load_stats(self, domain_or_url: str, method: Optional[str] = None) -> DomainPerfStats:
        """Load aggregated stats from SQLite or the in-memory fallback."""

        domain = self._extract_domain(domain_or_url)
        if not domain:
            return DomainPerfStats(domain="", attempts=0, successes=0, total_chars=0, last_ts=0.0)

        normalized = self._normalize_method(method) if method else None

        with self._lock:
            if self._sqlite_ok:
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        if normalized:
                            row = conn.execute(
                                """
                                SELECT COALESCE(SUM(attempts), 0), COALESCE(SUM(successes), 0),
                                       COALESCE(SUM(total_chars), 0), COALESCE(MAX(last_ts), 0)
                                FROM domain_perf
                                WHERE domain = ? AND method = ?
                                """,
                                (domain, normalized),
                            ).fetchone()
                        else:
                            row = conn.execute(
                                """
                                SELECT COALESCE(SUM(attempts), 0), COALESCE(SUM(successes), 0),
                                       COALESCE(SUM(total_chars), 0), COALESCE(MAX(last_ts), 0)
                                FROM domain_perf
                                WHERE domain = ?
                                """,
                                (domain,),
                            ).fetchone()

                    if row:
                        return DomainPerfStats(
                            domain=domain,
                            attempts=int(row[0] or 0),
                            successes=int(row[1] or 0),
                            total_chars=int(row[2] or 0),
                            last_ts=float(row[3] or 0.0),
                        )
                except Exception:
                    self._sqlite_ok = False

            return self._memory_aggregate(domain, method=normalized)

    # Lookup helpers.
    def get_success_rate(self, domain_or_url: str, method: Optional[str] = None) -> float:
        """Return the raw success rate for a domain and optional method."""

        stats = self._load_stats(domain_or_url, method=method)
        return stats.success_rate

    # Ranking helpers.
    def get_weighted_score(
        self,
        domain_or_url: str,
        method: Optional[str] = None,
        alpha: float = 2.0,
        beta: float = 2.0,
    ) -> float:
        """Return a Bayesian-smoothed domain score scaled by confidence."""

        stats = self._load_stats(domain_or_url, method=method)
        attempts = max(0, stats.attempts)
        successes = max(0, stats.successes)

        # Smooth sparse domains toward a neutral prior instead of overfitting small samples.
        bayes = (successes + alpha) / (attempts + alpha + beta)
        confidence = 1.0 - math.exp(-attempts / 10.0)

        # Discount domains whose successful responses are consistently too short.
        avg_chars = (stats.total_chars / successes) if successes > 0 else 0.0
        if successes == 0:
            quality = 1.0
        else:
            quality = 1.0 if avg_chars >= 400 else (0.75 if avg_chars >= 120 else 0.55)

        return max(0.0, min(1.0, bayes * (0.55 + 0.45 * confidence) * quality))

    # Lookup helpers.
    def get_stats(self, domain_or_url: str, method: Optional[str] = None) -> DomainPerfStats:
        """Return the full stats object for a domain and optional method."""

        return self._load_stats(domain_or_url, method=method)


# Singleton access helpers.
_store: Optional[DomainPerformanceStore] = None


# Singleton access helpers.
def get_domain_performance(db_path: Optional[str] = None) -> DomainPerformanceStore:
    """Return the shared domain-performance store instance."""

    global _store

    if _store is None:
        _store = DomainPerformanceStore(db_path=db_path)
    elif db_path and os.path.abspath(_store.db_path) != os.path.abspath(db_path):
        _store = DomainPerformanceStore(db_path=db_path)

    return _store
