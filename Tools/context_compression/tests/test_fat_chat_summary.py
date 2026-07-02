# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import re

import pytest

from context_compression.history_compressor import build_structured_history_summary
from context_compression.tests.cache_chat_utils import (
    collect_chat_entries,
    connect_cache_db,
    load_fattest_chat,
    resolve_cache_db_path,
)

RAW_NOISE_MARKERS = (
    "citation rules",
    "cite search evidence",
    "search results for:",
    "**site:**",
    "**url:**",
    "traceback",
    "exit_code",
)


# Count summary field values that look like raw tool or search noise.

def _count_noise(values: list[str]) -> int:
    return sum(
        1
        for value in values
        if any(marker in str(value).lower() for marker in RAW_NOISE_MARKERS)
        or str(value).lower().startswith("tool:")
        or str(value).lower().count("http://") + str(value).lower().count("https://") > 1
    )


# Exercise the bundled fat-chat fixture: model path, fallback path, and noise metrics.

def main() -> None:
    db_path = resolve_cache_db_path()
    if not db_path.exists():
        raise RuntimeError(f"Database not found: {db_path}")

    conn = connect_cache_db(db_path)
    fat = load_fattest_chat(conn)
    if fat is None:
        raise RuntimeError(f"No chats found in cache database: {db_path}")
    entries, recent = collect_chat_entries(conn, fat["id"])

    def valid_model_response(prompt_messages: list[dict[str, str]]) -> str:
        return "\n".join([
            "## Session Goal",
            "Real fat chat compression fixture.",
            "## Current Focus",
            "Validate structured compression on the bundled database.",
            "## Work Summary",
            "The bundled fat chat was loaded and sent through the model-summary path.",
            "## Reflection Summary",
            "The result came from model Markdown output parsed by deterministic code.",
            "## Recent User Messages",
            *[f"- {message}" for message in recent[:5]],
            "## Key Facts",
            "- Bundled fat chat fixture was exercised.",
            "## Files",
            "- None",
            "## URLs",
            "- None",
            "## Tools Used",
            "- None",
            "## Open Tasks",
            "- Verify that model Markdown is parsed and sanitized.",
            "## Risk Flags",
            "- None",
            "## Source Memory",
            "- user: real fixture loaded",
        ])

    # Unparseable model output must still preserve raw compressed context.
    _invalid_text, invalid_payload = build_structured_history_summary(
        overflow_entries=entries,
        recent_user_messages=recent,
        direct_user_directives=[],
        summarize_with_model=lambda _messages: "not structured",
        max_overflow_entries=120,
    )
    if not invalid_payload.get("source_memory"):
        raise AssertionError("Unparseable model output must preserve raw compressed context.")

    # An empty model response must fall back to raw harvest and say so in risk_flags.
    _empty_text, empty_payload = build_structured_history_summary(
        overflow_entries=entries,
        recent_user_messages=recent,
        direct_user_directives=[],
        summarize_with_model=lambda _messages: "",
        max_overflow_entries=120,
    )
    empty_flags = " ".join(str(flag) for flag in empty_payload.get("risk_flags") or [])
    if "empty summary output" not in empty_flags.lower():
        raise AssertionError("Empty model output must be flagged in risk_flags.")
    if not empty_payload.get("source_memory"):
        raise AssertionError("Empty model output must preserve raw compressed context.")

    # Valid Markdown model output must produce a non-empty semantic summary.
    summary_text, payload = build_structured_history_summary(
        overflow_entries=entries,
        recent_user_messages=recent,
        direct_user_directives=[],
        summarize_with_model=valid_model_response,
        max_overflow_entries=120,
    )
    if not payload.get("work_summary") or not payload.get("key_facts"):
        raise AssertionError("Model-backed compression produced an empty semantic summary.")

    key_facts = payload.get("key_facts") or []
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
    print("unparseable_model_preserved_raw:", bool(invalid_payload.get("source_memory")))
    print("summary_chars:", len(summary_text))
    print("noise:key_facts=", _count_noise(key_facts))
    print("noise:open_tasks=", _count_noise(open_tasks))
    print("noise:risk_flags=", _count_noise(risk_flags))
    print("noise:source_memory=", _count_noise(source_memory))
    print("suspicious_urls:", len(suspicious_urls))

    print("sample:key_facts:", (key_facts[:2] if isinstance(key_facts, list) else []))
    print("sample:source_memory:", (source_memory[:2] if isinstance(source_memory, list) else []))


# Pytest entry: skip when the bundled database is absent or has no chats.

@pytest.mark.integration
def test_fat_chat_summary_fixture() -> None:
    db_path = resolve_cache_db_path()
    if not db_path.exists():
        pytest.skip(f"Database not found: {db_path}")
    if load_fattest_chat(connect_cache_db(db_path)) is None:
        pytest.skip(f"No chats in cache database: {db_path}")
    main()


if __name__ == "__main__":
    main()
