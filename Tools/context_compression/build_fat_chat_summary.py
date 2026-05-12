from __future__ import annotations

import json
from pathlib import Path

from context_compression.cache_chat_utils import collect_chat_entries, connect_cache_db, load_fattest_chat
from context_compression.history_compressor import build_structured_history_summary


TOOL_DB_PATH = Path(__file__).with_name("db.sqlite3")
PROJECT_DB_PATH = Path(__file__).resolve().parents[2] / "db.sqlite3"
DB_PATH = TOOL_DB_PATH if TOOL_DB_PATH.exists() else PROJECT_DB_PATH
OUT_PATH = Path(__file__).with_name("test") / "fat_chat_summary.json"


def main() -> None:
    if not DB_PATH.exists():
        raise RuntimeError(f"Database not found: {DB_PATH}")

    conn = connect_cache_db(DB_PATH)
    fat = load_fattest_chat(conn)
    entries, recent_user_messages = collect_chat_entries(conn, fat["id"])

    summary_text, payload = build_structured_history_summary(
        overflow_entries=entries,
        recent_user_messages=recent_user_messages,
        direct_user_directives=[],
        summarize_with_model=None,
        max_overflow_entries=120,
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {
                "fat_chat": {
                    "id": fat["id"],
                    "title": fat["title"],
                    "messages": fat["messages"],
                    "chars": fat["chars"],
                },
                "summary_chars": len(summary_text),
                "summary_payload": payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Wrote: {OUT_PATH}")
    print(f"Chat: {fat['id']} ({fat['chars']} chars)")
    print(f"Summary chars: {len(summary_text)}")


if __name__ == "__main__":
    main()
