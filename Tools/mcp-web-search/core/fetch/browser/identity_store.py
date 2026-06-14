# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Persistent, family-keyed browser identity store.

Holds the *earned* browser state — Playwright storageState (cookies + localStorage
+ IndexedDB snapshot) — keyed by engine family, layered over the static personality
from Stage A (UA/platform/locale, which is generated, not stored).

Design (per the warm-browser contract, 2026-06-15):
  * SQLite on disk, modelled on profiles/runtime_profiles.py — the warm daemon is the
    primary writer (idle/recycle checkpoints); engine request builders read locally on
    the hot path with no IPC; MCP-side Set-Cookie capture writes under the same lock.
  * N most-recent *good* generations are kept per family. Memory/age recycle restores
    the latest; a captcha/burn rotates to an older good generation (a poisoned state is
    never the only backup), falling back to None → seed when none remain.
  * Cookies are family-bound: callers ask for a family's cookies and only replay them
    through that family's transport (mixing families is an anti-signal).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("core.fetch.browser.identity")

# How many generations to retain per family. Older ones are pruned, but the most
# recent good generation is always preserved as a rotation fallback.
_MAX_GENERATIONS = 5

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS identity_generations (
    family      TEXT    NOT NULL,
    generation  INTEGER NOT NULL,
    state       TEXT    NOT NULL,
    good        INTEGER NOT NULL DEFAULT 1,
    created     REAL    NOT NULL,
    PRIMARY KEY (family, generation)
);

CREATE INDEX IF NOT EXISTS idx_ident_family ON identity_generations(family);
"""


# True when a stored cookie domain applies to the given host (lenient suffix match).
def _domain_matches(cookie_domain: str, host: str) -> bool:
    cd = (cookie_domain or "").lstrip(".").lower()
    h = (host or "").lower()
    if not cd or not h:
        return False
    return h == cd or h.endswith("." + cd) or cd.endswith("." + h)


# Persistent per-family storageState store with generational good/burn backups.
class IdentityStore:

    def __init__(self, db_path: str, *, max_generations: int = _MAX_GENERATIONS) -> None:
        self._db_path = db_path
        self._max_generations = max(1, int(max_generations))
        self._local = threading.local()
        self._write_lock = threading.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # Per-thread persistent SQLite connection (WAL; readers never block the writer).
    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        with self._write_lock:
            conn = self._get_conn()
            for stmt in _SCHEMA_SQL.strip().split(";"):
                if stmt.strip():
                    conn.execute(stmt)
            conn.commit()

    # Persist a new generation of a family's storageState; returns its generation number.
    # good=False marks a checkpoint that should not be restored as-is (e.g. burned).
    def checkpoint(self, family: str, state: dict[str, Any], *, good: bool = True) -> int:
        family = (family or "").strip() or "default"
        try:
            blob = json.dumps(state, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as exc:
            logger.warning("identity_store: cannot serialise state for %r: %s", family, exc)
            return -1
        now = time.time()
        with self._write_lock:
            conn = self._get_conn()
            try:
                with conn:
                    row = conn.execute(
                        "SELECT COALESCE(MAX(generation), 0) AS g FROM identity_generations WHERE family = ?",
                        (family,),
                    ).fetchone()
                    generation = int(row["g"]) + 1
                    conn.execute(
                        "INSERT INTO identity_generations (family, generation, state, good, created) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (family, generation, blob, 1 if good else 0, now),
                    )
                    self._prune(conn, family)
                return generation
            except sqlite3.DatabaseError as exc:
                logger.warning("identity_store: checkpoint failed for %r: %s", family, exc)
                return -1

    # Keep the newest N generations, but never drop the most-recent good one.
    def _prune(self, conn: sqlite3.Connection, family: str) -> None:
        rows = conn.execute(
            "SELECT generation, good FROM identity_generations WHERE family = ? ORDER BY generation DESC",
            (family,),
        ).fetchall()
        if len(rows) <= self._max_generations:
            return
        keep = {int(r["generation"]) for r in rows[: self._max_generations]}
        newest_good = next((int(r["generation"]) for r in rows if int(r["good"]) == 1), None)
        if newest_good is not None:
            keep.add(newest_good)
        doomed = [int(r["generation"]) for r in rows if int(r["generation"]) not in keep]
        if doomed:
            conn.executemany(
                "DELETE FROM identity_generations WHERE family = ? AND generation = ?",
                [(family, g) for g in doomed],
            )

    # Most-recent generation with the given good flag, as a parsed storageState dict.
    def _fetch_state(self, family: str, *, good_only: bool) -> Optional[dict[str, Any]]:
        family = (family or "").strip() or "default"
        sql = "SELECT state FROM identity_generations WHERE family = ?"
        if good_only:
            sql += " AND good = 1"
        sql += " ORDER BY generation DESC LIMIT 1"
        try:
            row = self._get_conn().execute(sql, (family,)).fetchone()
        except sqlite3.DatabaseError as exc:
            logger.warning("identity_store: read failed for %r: %s", family, exc)
            return None
        if row is None:
            return None
        try:
            return json.loads(row["state"])
        except (TypeError, ValueError):
            return None

    # Latest good storageState to seed a fresh browser on start / memory recycle.
    def latest_good(self, family: str) -> Optional[dict[str, Any]]:
        return self._fetch_state(family, good_only=True)

    # Latest storageState regardless of good flag (diagnostics / forced restore).
    def latest(self, family: str) -> Optional[dict[str, Any]]:
        return self._fetch_state(family, good_only=False)

    # Burn the newest generation and return an older good one to rotate to (or None → seed).
    # Used on a captcha/burn recycle so a poisoned identity is not restored.
    def rotate(self, family: str) -> Optional[dict[str, Any]]:
        family = (family or "").strip() or "default"
        with self._write_lock:
            conn = self._get_conn()
            try:
                with conn:
                    top = conn.execute(
                        "SELECT generation FROM identity_generations WHERE family = ? "
                        "ORDER BY generation DESC LIMIT 1",
                        (family,),
                    ).fetchone()
                    if top is not None:
                        conn.execute(
                            "UPDATE identity_generations SET good = 0 WHERE family = ? AND generation = ?",
                            (family, int(top["generation"])),
                        )
            except sqlite3.DatabaseError as exc:
                logger.warning("identity_store: rotate failed for %r: %s", family, exc)
                return None
        return self.latest_good(family)

    # Cookies from the family's latest good state, optionally narrowed to a host.
    def cookies_for(self, family: str, *, host: str = "") -> list[dict[str, Any]]:
        state = self.latest_good(family)
        if not state:
            return []
        cookies = state.get("cookies") or []
        if not host:
            return list(cookies)
        return [c for c in cookies if _domain_matches(str(c.get("domain", "")), host)]

    # A ready "k=v; k2=v2" Cookie header for a host from the family's identity, or "".
    def cookie_header_for(self, family: str, host: str) -> str:
        pairs = [
            f"{c.get('name')}={c.get('value')}"
            for c in self.cookies_for(family, host=host)
            if c.get("name")
        ]
        return "; ".join(pairs)


_store: Optional[IdentityStore] = None
_store_lock = threading.Lock()

_DB_PATH = Path(__file__).resolve().parents[3] / "_cache" / "browser_identity.db"


# Lazily-initialised process-wide IdentityStore singleton.
def get_identity_store() -> IdentityStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = IdentityStore(str(_DB_PATH))
    return _store
