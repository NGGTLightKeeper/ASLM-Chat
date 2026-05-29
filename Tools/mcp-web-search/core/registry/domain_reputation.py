# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Dynamic domain reputation tracker.

Persists per-domain rolling quality scores in SQLite and auto-derives
blacklist and trust-promotion decisions when confidence is sufficient.

Design
------
Two tables:
  domain_reputation  — raw EWM stats per (domain, query_type)
  domain_decisions   — derived decisions (blacklist / promote)

Each scored result writes one observation to both:
  (domain, query_type)   — query-type-specialised score
  (domain, '__global__') — cross-type aggregate (used for blacklisting)

Thresholds
----------
  AUTO_BLACKLIST : global EMA < 0.12  AND obs_count >= 10
  AUTO_PROMOTE   : query_type EMA > 0.72 AND obs_count >= 15
  EMA_ALPHA      : 0.20  (≈ 10-obs half-life, recency-weighted)

Protection
----------
  Domains present in the static trust_registry with tier A or B are marked
  protected and are immune to auto-blacklisting. They can still be promoted.

Effect on scoring
-----------------
  - Auto-blacklisted domain → triage skips result entirely (hard gate).
  - Otherwise the reputation score (0–1) is blended into the trust component
    in _result_score: 70% static tier + 30% dynamic reputation (when static
    tier exists), or 100% dynamic reputation for unknown domains.
  - Reputation is only recorded when the result had actual fetched content
    (payload.text non-empty), so fetch failures do not penalise a domain.
  - Content signal (_content_quality_signal) blends quality, lexical overlap,
    and parsed/snippet relevance so BM25-default previews can reach promote EMA.
  - Auto-promoted tier (B/C) is applied to result.trust_tier when still unknown.

Public API
----------
DomainReputationStore   — main class
get_reputation_store()  — module-level singleton
DomainReport            — typed summary dataclass
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("core.registry.domain_reputation")

# ---------------------------------------------------------------------------
# Tuneable thresholds
# ---------------------------------------------------------------------------

EMA_ALPHA: float = 0.20           # recency weight; ≈10 obs half-life
BLACKLIST_THRESHOLD: float = 0.12  # global EMA below this → auto-blacklist
BLACKLIST_MIN_OBS: int = 10        # need at least N obs before blacklisting
PROMOTE_THRESHOLD: float = 0.72    # query_type EMA above this → promote
PROMOTE_MIN_OBS: int = 15          # need at least N obs before promoting
DEMOTION_THRESHOLD: float = 0.25   # promoted domain drops below this → demote
DEMOTION_MIN_OBS: int = 20         # obs needed to trigger demotion

# Minimum time a domain must remain blacklisted before recovery is evaluated.
# Prevents SEO farms that alternate quality from rapidly cycling in/out of blacklist.
UNBLACKLIST_COOLDOWN_HOURS: int = 24

# Synthetic query type used for the cross-type aggregate row
_GLOBAL = "__global__"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS domain_reputation (
    domain      TEXT NOT NULL,
    query_type  TEXT NOT NULL,
    obs_count   INTEGER DEFAULT 0,
    ema_score   REAL    DEFAULT 0.5,
    first_seen  REAL    NOT NULL,
    last_seen   REAL    NOT NULL,
    PRIMARY KEY (domain, query_type)
);

CREATE INDEX IF NOT EXISTS idx_dr_domain ON domain_reputation(domain);

CREATE TABLE IF NOT EXISTS domain_decisions (
    domain              TEXT PRIMARY KEY,
    protected           INTEGER DEFAULT 0,   -- 1 = immune to auto-blacklist
    auto_blacklisted    INTEGER DEFAULT 0,
    blacklisted_at      REAL,
    blacklist_ema       REAL,
    blacklist_obs       INTEGER,
    promoted_tier       TEXT,                -- NULL | 'C' | 'B'
    promoted_at         REAL,
    promoted_query_types TEXT DEFAULT '[]',  -- JSON array
    notes               TEXT DEFAULT ''
);
"""


# ---------------------------------------------------------------------------
# Dataclass for reporting
# ---------------------------------------------------------------------------

@dataclass
class DomainReport:
    domain: str
    global_ema: float
    global_obs: int
    per_type: dict[str, dict]          # query_type → {ema, obs}
    auto_blacklisted: bool
    blacklisted_at: Optional[float]
    promoted_tier: Optional[str]
    promoted_at: Optional[float]
    promoted_query_types: list[str]
    protected: bool


# ---------------------------------------------------------------------------
# DomainReputationStore
# ---------------------------------------------------------------------------

class DomainReputationStore:
    """SQLite-backed rolling domain reputation tracker.

    Thread-safe: all writes use a dedicated lock; reads use separate
    short-lived connections (WAL allows concurrent readers).
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = Lock()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()
        self._protect_static_domains()

    # -- Setup ---------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10, check_same_thread=False)
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

    def _protect_static_domains(self) -> None:
        """Mark A/B domains from the trust registry as protected (blacklist-immune)."""
        try:
            from core.registry.trust_registry import load_trust_registry

            _, _, domains = load_trust_registry()
            protected_patterns = {
                entry.pattern
                for entry in domains.values()
                if entry.tier in ("A", "B")
            }
        except Exception:
            protected_patterns = set()

        if not protected_patterns:
            return

        conn = self._connect()
        try:
            with conn:
                for pattern in protected_patterns:
                    conn.execute(
                        """
                        INSERT INTO domain_decisions (domain, protected)
                        VALUES (?, 1)
                        ON CONFLICT(domain) DO UPDATE SET protected = 1
                        """,
                        (pattern,),
                    )
        finally:
            conn.close()

    # -- Core write ----------------------------------------------------------

    def record(self, domain: str, query_type: str, score: float) -> None:
        """Record one content-quality observation for a domain.

        Writes to both (domain, query_type) and (domain, '__global__'), then
        re-evaluates whether auto-blacklist or auto-promote decisions should
        be updated.

        This method is synchronous and should be called from a thread pool
        executor in async contexts to avoid blocking the event loop.
        """
        if not domain or not (0.0 <= score <= 1.0):
            return

        now = time.time()
        with self._lock:
            conn = self._connect()
            try:
                self._upsert_ema(conn, domain, query_type, score, now)
                self._upsert_ema(conn, domain, _GLOBAL, score, now)
                conn.commit()
                self._evaluate_decisions(conn, domain, query_type)
                conn.commit()
            except Exception:
                logger.exception("domain_reputation.record failed for %s", domain)
            finally:
                conn.close()

    def _upsert_ema(
        self,
        conn: sqlite3.Connection,
        domain: str,
        query_type: str,
        score: float,
        now: float,
    ) -> None:
        row = conn.execute(
            "SELECT obs_count, ema_score FROM domain_reputation WHERE domain=? AND query_type=?",
            (domain, query_type),
        ).fetchone()

        if row is None:
            conn.execute(
                """
                INSERT INTO domain_reputation (domain, query_type, obs_count, ema_score,
                                              first_seen, last_seen)
                VALUES (?, ?, 1, ?, ?, ?)
                """,
                (domain, query_type, score, now, now),
            )
        else:
            new_ema = EMA_ALPHA * score + (1.0 - EMA_ALPHA) * row["ema_score"]
            conn.execute(
                """
                UPDATE domain_reputation
                SET obs_count = obs_count + 1, ema_score = ?, last_seen = ?
                WHERE domain = ? AND query_type = ?
                """,
                (new_ema, now, domain, query_type),
            )

    def _evaluate_decisions(
        self,
        conn: sqlite3.Connection,
        domain: str,
        query_type: str,
    ) -> None:
        """Re-check thresholds and update domain_decisions if needed."""
        now = time.time()

        # Read global stats
        g = conn.execute(
            "SELECT obs_count, ema_score FROM domain_reputation WHERE domain=? AND query_type=?",
            (domain, _GLOBAL),
        ).fetchone()
        if not g:
            return

        # Read existing decision row (if any)
        dec = conn.execute(
            "SELECT protected, auto_blacklisted, blacklisted_at, "
            "promoted_tier, promoted_query_types "
            "FROM domain_decisions WHERE domain=?",
            (domain,),
        ).fetchone()

        protected = bool(dec["protected"]) if dec else False
        currently_blacklisted = bool(dec["auto_blacklisted"]) if dec else False
        blacklisted_at = dec["blacklisted_at"] if dec else None
        promoted_tier = dec["promoted_tier"] if dec else None
        promoted_types_raw = (dec["promoted_query_types"] if dec else "[]") or "[]"
        try:
            promoted_types: list[str] = json.loads(promoted_types_raw)
        except Exception:
            promoted_types = []

        # -- Auto-blacklist --------------------------------------------------
        should_blacklist = (
            not protected
            and not currently_blacklisted
            and g["obs_count"] >= BLACKLIST_MIN_OBS
            and g["ema_score"] < BLACKLIST_THRESHOLD
        )
        # Cooldown: domain must stay blacklisted for at least UNBLACKLIST_COOLDOWN_HOURS
        # before recovery is evaluated. Prevents SEO farms from rapidly cycling
        # in/out by alternating content quality (high score → un-blacklist → abuse again).
        _cooldown_elapsed = (
            blacklisted_at is None
            or (now - blacklisted_at) >= UNBLACKLIST_COOLDOWN_HOURS * 3600
        )
        should_unblacklist = (
            currently_blacklisted
            and _cooldown_elapsed
            and g["obs_count"] >= BLACKLIST_MIN_OBS
            and g["ema_score"] >= BLACKLIST_THRESHOLD + 0.05  # hysteresis band
        )

        if should_blacklist:
            logger.warning(
                "auto-blacklisting %s: global_ema=%.3f obs=%d",
                domain, g["ema_score"], g["obs_count"],
            )
            self._upsert_decision(conn, domain, {
                "auto_blacklisted": 1,
                "blacklisted_at": now,
                "blacklist_ema": g["ema_score"],
                "blacklist_obs": g["obs_count"],
            })

        elif should_unblacklist:
            logger.info(
                "un-blacklisting %s: global_ema recovered to %.3f",
                domain, g["ema_score"],
            )
            self._upsert_decision(conn, domain, {
                "auto_blacklisted": 0,
                "blacklisted_at": None,
            })

        # -- Auto-promote / demote ------------------------------------------
        if query_type == _GLOBAL:
            return  # promote is per-query-type only

        qt = conn.execute(
            "SELECT obs_count, ema_score FROM domain_reputation WHERE domain=? AND query_type=?",
            (domain, query_type),
        ).fetchone()
        if not qt:
            return

        already_promoted_for_type = query_type in promoted_types

        if (
            not already_promoted_for_type
            and qt["obs_count"] >= PROMOTE_MIN_OBS
            and qt["ema_score"] >= PROMOTE_THRESHOLD
        ):
            new_types = promoted_types + [query_type]
            new_tier = "B" if len(new_types) >= 3 else "C"
            logger.info(
                "auto-promoting %s tier=%s for query_type=%s (ema=%.3f obs=%d)",
                domain, new_tier, query_type, qt["ema_score"], qt["obs_count"],
            )
            self._upsert_decision(conn, domain, {
                "promoted_tier": new_tier,
                "promoted_at": now,
                "promoted_query_types": json.dumps(new_types),
            })

        elif (
            already_promoted_for_type
            and qt["obs_count"] >= DEMOTION_MIN_OBS
            and qt["ema_score"] < DEMOTION_THRESHOLD
        ):
            new_types = [t for t in promoted_types if t != query_type]
            new_tier = promoted_tier if new_types else None
            logger.info(
                "demoting %s from query_type=%s (ema=%.3f)", domain, query_type, qt["ema_score"],
            )
            self._upsert_decision(conn, domain, {
                "promoted_tier": new_tier,
                "promoted_query_types": json.dumps(new_types),
            })

    def _upsert_decision(self, conn: sqlite3.Connection, domain: str, fields: dict) -> None:
        """Insert or patch a row in domain_decisions."""
        existing = conn.execute(
            "SELECT domain FROM domain_decisions WHERE domain=?", (domain,)
        ).fetchone()

        if existing is None:
            cols = ["domain"] + list(fields.keys())
            vals = [domain] + list(fields.values())
            placeholders = ", ".join("?" * len(vals))
            conn.execute(
                f"INSERT INTO domain_decisions ({', '.join(cols)}) VALUES ({placeholders})",
                vals,
            )
        else:
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE domain_decisions SET {set_clause} WHERE domain = ?",
                list(fields.values()) + [domain],
            )

    # -- Read API ------------------------------------------------------------

    def is_auto_blacklisted(self, domain: str) -> bool:
        """Return True if domain has been auto-blacklisted."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT auto_blacklisted FROM domain_decisions WHERE domain=?",
                (domain,),
            ).fetchone()
            return bool(row["auto_blacklisted"]) if row else False
        finally:
            conn.close()

    def get_reputation_score(self, domain: str, query_type: str) -> float:
        """Return the best available reputation score in [0, 1].

        Priority:
          1. Query-type-specific EMA if >= 5 observations
          2. Global EMA if >= 5 observations
          3. Neutral fallback (0.50)

        Only returns if the domain has enough observations to be meaningful;
        otherwise returns 0.50 so reputation is a no-op for new domains.
        """
        conn = self._connect()
        try:
            qt_row = conn.execute(
                "SELECT obs_count, ema_score FROM domain_reputation "
                "WHERE domain=? AND query_type=?",
                (domain, query_type),
            ).fetchone()
            if qt_row and qt_row["obs_count"] >= 5:
                return float(qt_row["ema_score"])

            g_row = conn.execute(
                "SELECT obs_count, ema_score FROM domain_reputation "
                "WHERE domain=? AND query_type=?",
                (domain, _GLOBAL),
            ).fetchone()
            if g_row and g_row["obs_count"] >= 5:
                return float(g_row["ema_score"])

            return 0.50
        finally:
            conn.close()

    def get_report(self, domain: str) -> Optional[DomainReport]:
        """Return a structured report for one domain, or None if unseen."""
        conn = self._connect()
        try:
            per_type_rows = conn.execute(
                """
                SELECT query_type, obs_count, ema_score
                FROM domain_reputation
                WHERE domain=?
                """,
                (domain,),
            ).fetchall()
            if not per_type_rows:
                return None

            per_type: dict[str, dict] = {}
            global_ema = 0.50
            global_obs = 0
            for row in per_type_rows:
                query_type = str(row["query_type"])
                data = {
                    "ema": float(row["ema_score"]),
                    "obs": int(row["obs_count"]),
                }
                if query_type == _GLOBAL:
                    global_ema = data["ema"]
                    global_obs = data["obs"]
                else:
                    per_type[query_type] = data

            dec = conn.execute(
                """
                SELECT protected, auto_blacklisted, blacklisted_at,
                       promoted_tier, promoted_at, promoted_query_types
                FROM domain_decisions
                WHERE domain=?
                """,
                (domain,),
            ).fetchone()

            promoted_query_types: list[str] = []
            if dec and dec["promoted_query_types"]:
                try:
                    promoted_query_types = list(json.loads(dec["promoted_query_types"]))
                except Exception:
                    promoted_query_types = []

            return DomainReport(
                domain=domain,
                global_ema=global_ema,
                global_obs=global_obs,
                per_type=per_type,
                auto_blacklisted=bool(dec["auto_blacklisted"]) if dec else False,
                blacklisted_at=dec["blacklisted_at"] if dec else None,
                promoted_tier=str(dec["promoted_tier"]) if dec and dec["promoted_tier"] else None,
                promoted_at=dec["promoted_at"] if dec else None,
                promoted_query_types=promoted_query_types,
                protected=bool(dec["protected"]) if dec else False,
            )
        finally:
            conn.close()

    def get_promoted_tier(self, domain: str) -> Optional[str]:
        """Return the promoted tier for a domain, if any."""
        report = self.get_report(domain)
        return report.promoted_tier if report else None

    def top_blacklisted(self, limit: int = 20) -> list[dict]:
        """Return recent auto-blacklisted domains ordered by blacklist time."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT domain, blacklist_ema, blacklist_obs, blacklisted_at
                FROM domain_decisions
                WHERE auto_blacklisted = 1
                ORDER BY COALESCE(blacklisted_at, 0) DESC, domain ASC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
            return [
                {
                    "domain": str(row["domain"]),
                    "blacklist_ema": float(row["blacklist_ema"]) if row["blacklist_ema"] is not None else None,
                    "blacklist_obs": int(row["blacklist_obs"]) if row["blacklist_obs"] is not None else 0,
                    "blacklisted_at": row["blacklisted_at"],
                }
                for row in rows
            ]
        finally:
            conn.close()

    def top_promoted(self, limit: int = 20) -> list[dict]:
        """Return promoted domains ordered by strongest tier then recency."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT domain, promoted_tier, promoted_at, promoted_query_types
                FROM domain_decisions
                WHERE promoted_tier IS NOT NULL
                ORDER BY CASE promoted_tier WHEN 'B' THEN 0 WHEN 'C' THEN 1 ELSE 2 END,
                         COALESCE(promoted_at, 0) DESC,
                         domain ASC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
            results: list[dict] = []
            for row in rows:
                try:
                    promoted_query_types = list(json.loads(row["promoted_query_types"] or "[]"))
                except Exception:
                    promoted_query_types = []
                results.append(
                    {
                        "domain": str(row["domain"]),
                        "promoted_tier": str(row["promoted_tier"]),
                        "promoted_at": row["promoted_at"],
                        "promoted_query_types": promoted_query_types,
                    }
                )
            return results
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_store: Optional[DomainReputationStore] = None
_store_lock = Lock()


def get_reputation_store() -> DomainReputationStore:
    """Return the lazily initialised global DomainReputationStore."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                from pathlib import Path as _Path
                db_path = str(
                    _Path(__file__).resolve().parents[2] / "_cache" / "domain_reputation.db"
                )
                _store = DomainReputationStore(db_path)
    return _store


# ---------------------------------------------------------------------------
# URL → domain helper (reused by callers)
# ---------------------------------------------------------------------------

def domain_from_url(url: str) -> str:
    """Extract bare hostname, stripping www. prefix."""
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""
