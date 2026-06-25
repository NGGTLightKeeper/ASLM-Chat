# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Persistent store for auto-harvested onion services (`_cache/onion_registry.db`).

Holds only entries discovered by anchored expansion — services whose TLS clearnet anchor
self-published an Onion-Location. The hand-vetted seed (onion_registry.json) stays in code
as the bootstrap; this DB is the growable, verified-by-anchor extension. Mirrors the other
_cache SQLite stores (per-thread WAL connection, write lock).
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from .models import OnionService

# store.py is at core/fetch/onion/ → parents[3] is the project root, where _cache/ lives
# alongside the other SQLite stores (hosted_cache.db, source_cache.db, domain_runtime.db).
_DB_PATH = Path(__file__).resolve().parents[3] / "_cache" / "onion_registry.db"


class OnionStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._write_lock = threading.Lock()
        self._local = threading.local()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        with self._write_lock:
            conn = self._get_conn()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS onion_services (
                    name            TEXT PRIMARY KEY,
                    category        TEXT NOT NULL,
                    clearnet_anchor TEXT NOT NULL,
                    onion           TEXT NOT NULL,
                    first_seen      REAL NOT NULL,
                    last_verified   REAL NOT NULL
                )
                """
            )
            conn.commit()

    # Insert or refresh a harvested service (keeps original first_seen).
    def upsert(self, service: OnionService) -> None:
        now = time.time()
        with self._write_lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO onion_services (name, category, clearnet_anchor, onion, first_seen, last_verified)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    category=excluded.category,
                    clearnet_anchor=excluded.clearnet_anchor,
                    onion=excluded.onion,
                    last_verified=excluded.last_verified
                """,
                (service.name, service.category, service.clearnet_anchor, service.onion, now, now),
            )
            conn.commit()

    # All harvested services as OnionService records.
    def list_all(self) -> tuple[OnionService, ...]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT name, category, clearnet_anchor, onion FROM onion_services"
        ).fetchall()
        return tuple(
            OnionService(name=r["name"], category=r["category"],
                         clearnet_anchor=r["clearnet_anchor"], onion=r["onion"])
            for r in rows
        )

    # Seconds since a name was last verified, or None if absent.
    def age_of(self, name: str) -> float | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT last_verified FROM onion_services WHERE name = ?", (name.lower(),)
        ).fetchone()
        return (time.time() - row["last_verified"]) if row else None


_store: OnionStore | None = None


def get_onion_store() -> OnionStore:
    global _store
    if _store is None:
        _store = OnionStore(str(_DB_PATH))
    return _store
