# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import json

import pytest

from custom_domains.reddit import (
    fetch_reddit_json,
    parse_reddit_json_payload,
    reddit_data_to_markdown,
    reddit_json_url,
)

REDDIT_LLM_TPS_URL = (
    "https://www.reddit.com/r/LLMDevs/comments/1ch0gt9/"
    "llm_inference_tokens_per_second_across_30_llms"
)

_SAMPLE_PAYLOAD = [
    {
        "data": {
            "children": [
                {
                    "data": {
                        "subreddit": "LLMDevs",
                        "author": "tester",
                        "score": 42,
                        "title": "LLM inference tokens per second across 30 LLMs",
                        "selftext": "Benchmark notes.",
                    }
                }
            ]
        }
    },
    {
        "data": {
            "children": [
                {
                    "kind": "t1",
                    "data": {
                        "author": "reply_user",
                        "score": 3,
                        "body": "vLLM is fast on H100.",
                        "replies": "",
                    },
                }
            ]
        }
    },
]


def test_reddit_json_url_appends_suffix() -> None:
    assert reddit_json_url(REDDIT_LLM_TPS_URL).endswith(
        "/llm_inference_tokens_per_second_across_30_llms.json?limit=50&depth=3"
    )


def test_parse_reddit_json_payload_from_raw_json() -> None:
    raw = json.dumps(_SAMPLE_PAYLOAD)
    assert parse_reddit_json_payload(raw) == _SAMPLE_PAYLOAD


def test_reddit_data_to_markdown_includes_post_and_comment() -> None:
    md = reddit_data_to_markdown(_SAMPLE_PAYLOAD, REDDIT_LLM_TPS_URL)
    assert "LLM inference tokens per second" in md
    assert "vLLM is fast on H100" in md


def test_fetch_reddit_json_uses_camoufox_when_curl_blocked(monkeypatch) -> None:
    def fail_curl(*args, **kwargs):
        raise RuntimeError("HTTP Error 403")

    async def fake_camoufox(thread_url: str, timeout: float):
        assert thread_url == REDDIT_LLM_TPS_URL
        return _SAMPLE_PAYLOAD

    monkeypatch.setattr("custom_domains.reddit._fetch_reddit_json_curl", fail_curl)
    monkeypatch.setattr("custom_domains.reddit._fetch_reddit_json_camoufox", fake_camoufox)

    markdown = asyncio.run(fetch_reddit_json(REDDIT_LLM_TPS_URL, timeout=10.0))
    assert "vLLM is fast on H100" in markdown


@pytest.mark.integration
def test_fetch_reddit_json_live_llm_tps_thread() -> None:
    markdown = asyncio.run(fetch_reddit_json(REDDIT_LLM_TPS_URL, timeout=45.0))
    if markdown.startswith("Error:"):
        pytest.skip(markdown[:200])
    assert len(markdown) > 300
    lowered = markdown.lower()
    assert "token" in lowered or "inference" in lowered
