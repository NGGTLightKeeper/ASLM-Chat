# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

# Tool root (context_compression/) and the ASLM-Chat project root.
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Where dev scripts write their JSON reports (gitignored).
REPORTS_DIR = Path(__file__).resolve().parent / "out"


# The chat cache database: the copy dropped into the tool root wins, else the live project DB.
def resolve_cache_db_path() -> Path:
    tool_db = PACKAGE_ROOT / "db.sqlite3"
    return tool_db if tool_db.exists() else PROJECT_ROOT / "db.sqlite3"


# Open the chat cache SQLite database with row dict access.
def connect_cache_db(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


# Return the chat row with the largest combined message content footprint, or None when empty.
def load_fattest_chat(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """
        select c.id, c.title, count(m.id) as messages,
               sum(length(m.content) + length(coalesce(m.llm_transcript,''))) as chars
        from Data_chat c
        join Data_message m on m.chat_id = c.id
        group by c.id
        order by chars desc
        limit 1
        """
    ).fetchone()


# Load transcript entries and the latest user messages for compression input.
def collect_chat_entries(conn: sqlite3.Connection, chat_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    rows = conn.execute(
        """
        select id, role, content, llm_transcript, created_at
        from Data_message
        where chat_id=?
        order by created_at, id
        """,
        (chat_id,),
    ).fetchall()

    entries: list[dict[str, Any]] = []
    for row in rows:
        transcript_raw = row["llm_transcript"] or "[]"
        try:
            transcript = json.loads(transcript_raw)
        except Exception:
            transcript = []

        # Prefer per-turn LLM transcript items when present.
        if isinstance(transcript, list) and transcript:
            for item in transcript:
                if not isinstance(item, dict):
                    continue
                entry = dict(item)
                entry.setdefault("role", row["role"])
                if not entry.get("content") and row["content"]:
                    entry["content"] = row["content"]
                entries.append(entry)
            continue

        if row["content"]:
            entries.append({"role": row["role"], "content": row["content"]})

    recent_user_messages = [
        str(row["content"] or "").strip()[:1200]
        for row in reversed(rows)
        if str(row["role"]).lower() == "user" and str(row["content"] or "").strip()
    ][:5]

    return entries, recent_user_messages
