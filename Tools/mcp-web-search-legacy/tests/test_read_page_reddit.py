# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

# Reddit read_page uses .json suffix via curl_cffi, then camoufox on the same URL.
# Live check (network + browser, slow):
#   pytest tests/test_read_page_reddit.py -m integration -q

from __future__ import annotations

import asyncio

import pytest

from services.read_page import ReadPageOptions, ReadPageService

REDDIT_LLM_TPS_URL = (
    "https://www.reddit.com/r/LLMDevs/comments/1ch0gt9/"
    "llm_inference_tokens_per_second_across_30_llms"
)


def test_read_page_reddit_does_not_fall_through_to_html_on_json_failure(monkeypatch) -> None:
    async def fail_reddit_json(url: str, timeout: float = 15.0) -> str:
        return "Error: Reddit fetch failed: camoufox blocked"

    async def fail_camoufox_html(self, url: str, opts) -> str:
        raise AssertionError("reddit read_page must not fetch generic HTML via camoufox")

    monkeypatch.setattr("services.read_page._fetch_reddit_json", fail_reddit_json)
    monkeypatch.setattr(ReadPageService, "_fetch_camoufox_raw_html", fail_camoufox_html)

    markdown, _ = asyncio.run(ReadPageService().read_with_trace(REDDIT_LLM_TPS_URL))
    assert "blocked by network security" not in markdown.lower()
    assert markdown.startswith("Error: Reddit fetch failed")


def test_read_page_reddit_uses_custom_json_fetch(monkeypatch) -> None:
    async def fake_reddit_json(url: str, timeout: float = 15.0) -> str:
        return (
            "# LLM inference tokens per second across 30 LLMs\n\n"
            "Benchmark table comparing throughput on consumer and datacenter GPUs.\n\n"
            "[reply_user | +3] vLLM is fast on H100."
        )

    monkeypatch.setattr("services.read_page._fetch_reddit_json", fake_reddit_json)

    markdown, attempts = asyncio.run(
        ReadPageService().read_with_trace(REDDIT_LLM_TPS_URL)
    )

    assert "tokens per second" in markdown.lower()
    assert "vLLM is fast on H100" in markdown
    assert attempts == []


@pytest.mark.integration
def test_read_page_reddit_live_llm_tps_thread() -> None:
    service = ReadPageService(ReadPageOptions(timeout=45.0))
    markdown, attempts = asyncio.run(service.read_with_trace(REDDIT_LLM_TPS_URL))

    if markdown.lstrip().lower().startswith("error:"):
        pytest.skip(f"reddit live fetch blocked: {markdown[:200]}")

    assert len(markdown) > 300
    lowered = markdown.lower()
    assert "token" in lowered or "llm" in lowered or "inference" in lowered
