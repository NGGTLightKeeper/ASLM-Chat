# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio

import core.search.web_search as search_module
from core.config.settings import RoutingSection
from core.search.router import ProviderDescriptor, SearchPressureController


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class _Tracker:
    def allow(self, _name: str) -> bool:
        return True

    def is_healthy(self, _name: str) -> bool:
        return True


def _plans(count: int, vertical: str = "web") -> list[dict]:
    return [{"vertical": vertical, "compiled_query": f"q{index}"} for index in range(count)]


def _decide(controller, clock, *, count=1, apis=0, scope="generation:g"):
    providers = [
        ProviderDescriptor(f"api{index}", "api", "google" if index < 2 else f"f{index}")
        for index in range(apis)
    ]
    return controller.decide(
        _plans(count), scope=scope, api_providers=providers, tracker=_Tracker(),
        enabled_scrapers={
            "google": True, "duckduckgo": True, "startpage": True,
            "qwant": True, "brave": True, "yandex": False, "yep": False,
        },
        cfg=RoutingSection(),
    )


def test_api_relief_counts_transports_but_deduplicates_families():
    clock = _Clock()
    decision = _decide(SearchPressureController(clock=clock), clock, count=1, apis=2)
    assert decision.api_relief_factor == 0.70
    assert decision.api_providers == ("api0", "api1")
    assert decision.api_families == ("google",)
    assert len(decision.reserve_scrapers) == 2


def test_rapid_batching_reaches_api_only_t4_and_trims_tail():
    clock = _Clock()
    controller = SearchPressureController(clock=clock)
    decisions = []
    for _ in range(8):
        decisions.append(_decide(controller, clock, count=4))
        clock.now += 0.25
    assert decisions[0].admitted_count == 4
    assert decisions[-1].level_name == "T4"
    assert decisions[-1].admitted_count == 1
    assert decisions[-1].primary_scrapers == ()
    assert decisions[-1].dropped_indices == (2, 3, 4)


def test_idle_recovery_discards_remainder_and_generation_isolated():
    clock = _Clock()
    controller = SearchPressureController(clock=clock)
    for _ in range(8):
        saturated = _decide(controller, clock, count=4)
        clock.now += 0.25
    assert saturated.level_name == "T4"

    clock.now += 8.0
    recovered = _decide(controller, clock, count=1)
    assert recovered.level_name == "T3"
    fresh = _decide(controller, clock, count=1, scope="generation:new")
    assert fresh.level_name == "normal"


def test_single_normal_gets_browser_and_batch_does_not():
    clock = _Clock()
    single = _decide(SearchPressureController(clock=clock), clock, count=1)
    batch = _decide(SearchPressureController(clock=clock), clock, count=2)
    assert single.browser_permits == 1
    assert batch.browser_permits == 0
    assert len(single.primary_by_query[0]) > len(batch.primary_by_query[0])


def test_enabled_yandex_leads_a_narrow_primary_wave():
    clock = _Clock()
    controller = SearchPressureController(clock=clock)
    decision = controller.decide(
        _plans(4), scope="generation:yandex", api_providers=[], tracker=_Tracker(),
        enabled_scrapers={
            "google": True, "duckduckgo": True, "startpage": True,
            "qwant": True, "brave": True, "yandex": True, "yep": True,
        },
        cfg=RoutingSection(),
    )
    assert decision.primary_by_query[0][0] == "yandex"


def test_failed_primary_promotes_one_cold_reserve(monkeypatch):
    calls: list[str] = []

    class Primary:
        name = "primary"
        status = "error"

    class Reserve:
        name = "reserve"
        status = "success"

    class FakeSerpApi:
        def __init__(self, *, engines, **_kwargs):
            self.engine = engines[0]

        async def search_stream(self, *_args, **_kwargs):
            calls.append(self.engine.name)
            yield {
                "type": "engine",
                "payload": {
                    "engine": self.engine.name,
                    "status": self.engine.status,
                    "fetch_ms": 1,
                    "sources": [] if self.engine.status == "error" else [{}],
                },
            }

    monkeypatch.setattr(search_module, "SerpApi", FakeSerpApi)

    async def run():
        return [event async for event in search_module._routed_event_stream(
            "q", primary_engines=(Primary,), reserve_engines=(Reserve,),
            hosted_stream=None, region="us-en", safesearch="moderate",
            timelimit=None, deadline=5.0,
        )]

    asyncio.run(run())
    assert calls == ["primary", "reserve"]


def test_api_source_keeps_t4_scrapers_asleep(monkeypatch):
    calls: list[str] = []

    class Reserve:
        name = "reserve"

    class FakeSerpApi:
        def __init__(self, *, engines, **_kwargs):
            calls.append(engines[0].name)

        async def search_stream(self, *_args, **_kwargs):
            if False:
                yield None

    async def hosted():
        yield {
            "type": "source", "engine": "hosted:tavily", "provider_family": "tavily",
            "rank": 1, "url": {"url": "https://example.com", "host": "example.com"},
            "serp": {"title": "x", "snippet": "y"},
        }

    monkeypatch.setattr(search_module, "SerpApi", FakeSerpApi)

    async def run():
        return [event async for event in search_module._routed_event_stream(
            "q", primary_engines=(), reserve_engines=(Reserve,),
            hosted_stream=hosted(), region="us-en", safesearch="moderate",
            timelimit=None, deadline=5.0,
        )]

    events = asyncio.run(run())
    assert events and calls == []
