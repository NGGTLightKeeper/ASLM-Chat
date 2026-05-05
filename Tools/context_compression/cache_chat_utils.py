from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def connect_cache_db(db_path: Path) -> sqlite3.Connection:
    """Open chat cache database with Row access."""

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def load_fattest_chat(conn: sqlite3.Connection) -> sqlite3.Row:
    """Return the chat with the largest stored content/transcript footprint."""

    row = conn.execute(
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
    if row is None:
        raise RuntimeError("No chats found in cache database.")
    return row


def collect_chat_entries(conn: sqlite3.Connection, chat_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Collect normalized transcript entries and latest user messages for compression."""

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
