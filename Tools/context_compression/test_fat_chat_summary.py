from __future__ import annotations

import re
from pathlib import Path

from context_compression.cache_chat_utils import collect_chat_entries, connect_cache_db, load_fattest_chat
from context_compression.history_compressor import build_structured_history_summary


DB_PATH = Path(__file__).resolve().parents[2] / "db.sqlite3"
RAW_NOISE_MARKERS = (
    "citation rules",
    "cite search evidence",
    "search results for:",
    "**site:**",
    "**url:**",
    "traceback",
    "exit_code",
)


def _count_noise(values: list[str]) -> int:
    return sum(
        1
        for value in values
        if any(marker in str(value).lower() for marker in RAW_NOISE_MARKERS)
        or str(value).lower().startswith("tool:")
        or str(value).lower().count("http://") + str(value).lower().count("https://") > 1
    )


def main() -> None:
    if not DB_PATH.exists():
        raise RuntimeError(f"Database not found: {DB_PATH}")

    conn = connect_cache_db(DB_PATH)
    fat = load_fattest_chat(conn)
    entries, recent = collect_chat_entries(conn, fat["id"])

    summary_text, payload = build_structured_history_summary(
        overflow_entries=entries,
        recent_user_messages=recent,
        direct_user_directives=recent,
        summarize_with_model=None,
        max_overflow_entries=120,
    )

    key_facts = payload.get("key_facts") or []
    decisions = payload.get("decisions_and_rationale") or []
    open_tasks = payload.get("open_tasks") or []
    risk_flags = payload.get("risk_flags") or []
    source_memory = payload.get("source_memory") or []
    urls = (payload.get("artifacts") or {}).get("urls") or []

    suspicious_urls = [
        url
        for url in urls
        if re.search(r"https?://(127\.0\.0\.1|localhost|([^/]+\.)?bing\.com)(:|/|$)", str(url), re.IGNORECASE)
    ]

    print("fat_chat_id:", fat["id"])
    print("fat_chat_title:", fat["title"])
    print("fat_chat_chars:", fat["chars"])
    print("entries:", len(entries))
    print("summary_chars:", len(summary_text))
    print("noise:key_facts=", _count_noise(key_facts))
    print("noise:decisions=", _count_noise(decisions))
    print("noise:open_tasks=", _count_noise(open_tasks))
    print("noise:risk_flags=", _count_noise(risk_flags))
    print("noise:source_memory=", _count_noise(source_memory))
    print("suspicious_urls:", len(suspicious_urls))

    print("sample:key_facts:", (key_facts[:2] if isinstance(key_facts, list) else []))
    print("sample:source_memory:", (source_memory[:2] if isinstance(source_memory, list) else []))


if __name__ == "__main__":
    main()
