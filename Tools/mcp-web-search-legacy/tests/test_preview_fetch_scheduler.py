# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio

from core.extract.content_processor import PreviewPayload
from core.models.search import SearchResult
from services import web_search
from services.web_search import TriageResult, _build_preview_fetch_plan, _fetch_previews


def _result(name: str) -> SearchResult:
    return SearchResult(
        url=f"https://{name}.example/page",
        title=f"{name} title",
        snippet=f"{name} snippet with enough text to pass candidate triage.",
    )


def test_preview_fetch_plan_prioritizes_score_and_preserves_indices() -> None:
    results = [_result("first"), _result("best"), _result("skip"), _result("second")]
    triage = [
        TriageResult(skip=False, fetch_policy="cheap", score=0.30),
        TriageResult(skip=False, fetch_policy="race", score=0.90),
        TriageResult(skip=True, fetch_policy="cheap", score=1.00),
        TriageResult(skip=False, fetch_policy="race", score=0.70),
    ]

    plan = _build_preview_fetch_plan(results, triage, limit=3)

    assert plan.indices == [1, 3, 0]
    assert plan.results == [results[1], results[3], results[0]]
    assert plan.policies == ["race", "race", "cheap"]
    assert plan.scores == [0.90, 0.70, 0.30]


def test_preview_fetcher_holds_low_score_sources_in_reserve(monkeypatch) -> None:
    async def run() -> None:
        results = [_result("high-one"), _result("high-two"), _result("low")]
        started: list[str] = []
        release_high = asyncio.Event()

        async def fake_fetch(_session, result, *_args, **_kwargs):
            name = result.url.split("//", 1)[1].split(".", 1)[0]
            started.append(name)
            if name.startswith("high"):
                await release_high.wait()
            return PreviewPayload(text=f"parsed {name}")

        monkeypatch.setattr(web_search, "_fetch_preview_one", fake_fetch)
        monkeypatch.setattr(web_search, "warm_preview_models", lambda _settings: None)

        task = asyncio.create_task(
            _fetch_previews(
                results,
                query="test",
                concurrency=3,
                fetch_timeout=1.0,
                total_timeout=2.0,
                preview_settings={},
                loop=asyncio.get_running_loop(),
                priorities=[0.90, 0.80, 0.20],
            )
        )

        for _ in range(20):
            if len(started) >= 2:
                break
            await asyncio.sleep(0.01)

        assert started == ["high-one", "high-two"]
        release_high.set()
        payloads = await task

        assert started == ["high-one", "high-two", "low"]
        assert [payload.text for payload in payloads] == [
            "parsed high-one",
            "parsed high-two",
            "parsed low",
        ]

    asyncio.run(run())
