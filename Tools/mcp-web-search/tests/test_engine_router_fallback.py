import time
import base64
import threading

from core.ddgs.ddgs import DDGS
from core.ddgs.engines import ENGINES
from core.ddgs.engines.bing import Bing
from core.ddgs.results import TextResult
from core.ddgs.routing import PROFILES, ROUTING_STATE, HealthState, RoutingState, infer_language
from core.fetch import ddgs_client
from core.fetch.engine_stats import BACKUP_ENGINES, PRIMARY_ENGINES


def test_ddgs_client_uses_vendored_search_core() -> None:
    assert ddgs_client._DDGS_AVAILABLE is True
    assert ddgs_client.DDGS.__module__ == "core.ddgs"


def test_router_backends_exist_in_vendored_search_core() -> None:
    assert set(PRIMARY_ENGINES + BACKUP_ENGINES) <= set(ENGINES["text"])


def test_provider_family_links_are_explicit() -> None:
    assert PROFILES["duckduckgo"].provider == PROFILES["yahoo"].provider == PROFILES["bing"].provider == "bing"
    assert PROFILES["google"].provider == PROFILES["startpage"].provider == "google"


def test_chinese_plan_avoids_duckduckgo_and_yahoo_pair() -> None:
    state = RoutingState()
    plan = state.plan(
        {"duckduckgo", "yahoo", "google", "brave"},
        language="zh",
        query_types={"general"},
        max_attempts=2,
    )

    assert "yahoo" in plan
    assert "duckduckgo" not in plan
    assert len({PROFILES[name].provider for name in plan}) == 2


def test_related_provider_is_allowed_when_only_fallback_left() -> None:
    state = RoutingState()
    plan = state.plan(
        {"google", "startpage"},
        language="en",
        query_types={"general"},
        max_attempts=2,
    )

    assert plan == ["google", "startpage"]


def test_recent_provider_is_temporarily_deprioritized() -> None:
    state = RoutingState()
    state.provider("google").last_used_at = time.time()

    plan = state.plan(
        {"google", "brave"},
        language="en",
        query_types={"technical"},
        max_attempts=1,
    )

    assert plan == ["brave"]


def test_suspended_engine_is_skipped() -> None:
    state = RoutingState()
    state.engine("google").suspended_until = time.time() + 60

    plan = state.plan(
        {"google", "brave", "yandex"},
        language="en",
        query_types={"general"},
        max_attempts=2,
    )

    assert "google" not in plan


def test_normal_plan_reserves_b_tier_after_a_tier() -> None:
    state = RoutingState()

    plan = state.plan(
        {"google", "brave", "bing", "mojeek"},
        language="en",
        query_types={"general"},
        max_attempts=2,
    )

    assert PROFILES[plan[0]].tier == "A"
    assert PROFILES[plan[1]].tier == "B"


def test_quality_plan_prefers_provider_diversity_without_forced_b_tier() -> None:
    state = RoutingState()

    plan = state.plan(
        {"google", "brave", "bing", "mojeek"},
        language="en",
        query_types={"general"},
        max_attempts=3,
        routing_profile="quality",
    )

    assert plan[:2] == ["google", "brave"]
    assert len({PROFILES[name].provider for name in plan}) == len(plan)


def test_quality_journalistic_plan_prefers_specialized_news_engine() -> None:
    state = RoutingState()

    plan = state.plan(
        {"google", "brave", "brave_news", "bing", "bing_news"},
        language="en",
        query_types={"journalistic"},
        max_attempts=4,
        routing_profile="quality",
    )

    assert plan[0] == "brave_news"
    assert "bing_news" not in plan[:2]


def test_stability_journalistic_plan_uses_specialist_on_first_wave() -> None:
    state = RoutingState()

    plan = state.plan(
        {"google", "brave", "brave_news", "bing", "bing_news"},
        language="en",
        query_types={"general", "journalistic"},
        class_weights={"journalistic": 0.75, "general": 0.25},
        max_attempts=2,
    )

    assert plan[0] == "brave_news"
    assert PROFILES[plan[1]].tier == "A"


def test_weighted_technical_class_prioritizes_google_before_first_request() -> None:
    state = RoutingState()

    plan = state.plan(
        {"google", "duckduckgo", "brave"},
        language="en",
        query_types={"general", "technical"},
        class_weights={"technical": 0.8, "general": 0.2},
        max_attempts=1,
    )

    assert plan == ["google"]


def test_secondary_journalistic_class_does_not_displace_general_engines() -> None:
    state = RoutingState()

    plan = state.plan(
        {"google", "brave", "brave_news", "bing"},
        language="en",
        query_types={"general", "journalistic"},
        class_weights={"general": 0.8, "journalistic": 0.2},
        max_attempts=2,
    )

    assert plan[0] != "brave_news"
    assert {PROFILES[name].tier for name in plan} == {"A", "B"}


def test_weighted_routing_keeps_language_preference() -> None:
    state = RoutingState()

    plan = state.plan(
        {"google", "brave", "bing", "yandex"},
        language="ru",
        query_types={"technical"},
        class_weights={"technical": 1.0},
        max_attempts=2,
    )

    assert "yandex" in plan


def test_first_forbidden_uses_short_cooldown(monkeypatch) -> None:
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    state = RoutingState()

    state.record("google", latency=0.5, success=False, error=RuntimeError("HTTP 403 forbidden"))

    assert 7.0 <= state.engine("google").suspended_until - now <= 9.0


def test_success_clears_engine_cooldown() -> None:
    state = RoutingState()
    state.engine("google").suspended_until = time.time() + 60

    state.record("google", latency=0.5, success=True)

    assert state.engine("google").suspended_until == 0.0


def test_quality_concurrency_throttles_after_systematic_timeouts() -> None:
    state = RoutingState()

    assert state.quality_concurrency({"google", "brave"}) == 2
    state.record("google", latency=1.0, success=False, error=TimeoutError("timed out"))
    state.record("brave", latency=1.0, success=False, error=TimeoutError("timed out"))

    assert state.quality_concurrency({"google", "brave"}) == 1
    state.record("google", latency=0.5, success=True)
    state.record("brave", latency=0.5, success=True)
    assert state.quality_concurrency({"google", "brave"}) == 2


def test_bing_direct_engine_decodes_redirect_url() -> None:
    target = "https://docs.python.org/3/library/asyncio-task.html"
    encoded = base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
    result = TextResult(
        title="asyncio task docs",
        href=f"https://www.bing.com/ck/a?u=a1{encoded}&ntb=1",
        body="docs",
    )

    output = Bing.post_extract_results(None, [result])

    assert output[0].href == target


def test_bing_direct_engine_uses_curl_cffi(monkeypatch) -> None:
    calls = []

    class Response:
        status_code = 200
        text = "<html></html>"

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return Response()

    from curl_cffi import requests as cffi_req

    monkeypatch.setattr(cffi_req, "request", fake_request)
    engine = Bing(timeout=7)

    assert engine.request("GET", "https://www.bing.com/search", params={"q": "test"}) == "<html></html>"
    assert calls[0][2]["impersonate"] == "chrome124"
    assert calls[0][2]["timeout"] == 7.0


def test_p95_reduces_attempt_timeout() -> None:
    state = RoutingState()
    state.engines["google"] = HealthState(latencies=__import__("collections").deque([1.0, 2.0, 3.0], maxlen=30))

    assert state.attempt_timeout("google", 10.0) == 5.0


def test_health_state_persists_between_workers(tmp_path) -> None:
    db = tmp_path / "routing.sqlite"
    first = RoutingState(db)
    first.record("google", latency=1.5, success=True)

    second = RoutingState(db)
    second.plan({"google", "brave"}, language="en", query_types={"technical"}, max_attempts=1)

    assert second.engine("google").p50 == 1.5
    assert second.engine("google").successes == 1


def test_timeout_pressure_persists_between_workers(tmp_path) -> None:
    db = tmp_path / "routing.sqlite"
    first = RoutingState(db)
    first.record("google", latency=1.5, success=False, error=TimeoutError("timed out"))
    first.record("brave", latency=1.5, success=False, error=TimeoutError("timed out"))

    second = RoutingState(db)
    second.plan({"google", "brave"}, language="en", query_types={"technical"}, max_attempts=2)

    assert second.quality_concurrency({"google", "brave"}) == 1


def test_unicode_language_detection_is_owned_by_ddgs_core() -> None:
    assert infer_language("\u043a\u0430\u043a \u043d\u0430\u0441\u0442\u0440\u043e\u0438\u0442\u044c nginx") == "ru"
    assert infer_language("\u4eba\u5de5\u667a\u80fd \u6700\u65b0\u6d88\u606f") == "zh"
    assert infer_language("\ud55c\uad6d \ub274\uc2a4") == "ko"


def test_auto_search_runs_engines_sequentially_and_preserves_origin(monkeypatch) -> None:
    calls: list[str] = []
    timeouts: list[float] = []

    class FakeResult:
        def __init__(self, url: str) -> None:
            self.title = url
            self.href = url
            self.body = "body"

    class FakeEngine:
        def __init__(self, name: str) -> None:
            self.name = name

        def search(self, *_args, **_kwargs):
            calls.append(self.name)
            return [FakeResult(f"https://{self.name}.example/{i}") for i in range(4)]

    monkeypatch.setattr(
        ROUTING_STATE,
        "plan",
        lambda *_args, **_kwargs: ["google", "brave"],
    )
    monkeypatch.setattr(ROUTING_STATE, "record", lambda *_args, **_kwargs: None)
    def fake_engine(_self, name, timeout):
        timeouts.append(timeout)
        return FakeEngine(name)

    monkeypatch.setattr(DDGS, "_engine", fake_engine)

    results = DDGS(timeout=5).text("query", backend="auto", max_results=4, max_attempts=2)

    assert calls == ["google", "brave"]
    assert timeouts[0] <= 2.5
    assert [result["_engine"] for result in results] == ["google", "google", "brave", "brave"]


def test_auto_search_replans_to_b_tier_after_a_error(monkeypatch) -> None:
    calls: list[str] = []

    class FakeResult:
        def __init__(self) -> None:
            self.title = "Bing result"
            self.href = "https://bing.example/result"
            self.body = "body"

    class FakeEngine:
        def __init__(self, name: str) -> None:
            self.name = name

        def search(self, *_args, **_kwargs):
            calls.append(self.name)
            if self.name == "google":
                raise RuntimeError("HTTP 403 forbidden")
            return [FakeResult()]

    def fake_plan(available, *, prefer_tier=None, **_kwargs):
        if prefer_tier == "B":
            return ["bing"] if "bing" in available else []
        return [name for name in ("google", "brave", "bing") if name in available]

    monkeypatch.setattr(ROUTING_STATE, "plan", fake_plan)
    monkeypatch.setattr(ROUTING_STATE, "record", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(DDGS, "_engine", lambda _self, name, _timeout: FakeEngine(name))

    results = DDGS(timeout=5).text("query", backend="auto", max_results=1, max_attempts=1)

    assert calls == ["google", "bing"]
    assert results[0]["_engine"] == "bing"


def test_quality_search_counts_only_engines_that_add_unique_results(monkeypatch) -> None:
    calls: list[str] = []

    class FakeResult:
        def __init__(self, url: str) -> None:
            self.title = url
            self.href = url
            self.body = "body"

    class FakeEngine:
        def __init__(self, name: str) -> None:
            self.name = name

        def search(self, *_args, **_kwargs):
            calls.append(self.name)
            if self.name == "brave":
                return [FakeResult("https://google.example/result")]
            return [FakeResult(f"https://{self.name}.example/result")]

    monkeypatch.setattr(
        ROUTING_STATE,
        "plan",
        lambda *_args, **_kwargs: ["google", "brave", "bing", "yandex"],
    )
    monkeypatch.setattr(ROUTING_STATE, "record", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(DDGS, "_engine", lambda _self, name, _timeout: FakeEngine(name))

    rows = DDGS(timeout=10).text(
        "query",
        backend="auto",
        max_results=10,
        max_attempts=3,
        routing_profile="quality",
    )

    assert set(calls) == {"google", "brave", "bing", "yandex"}
    assert {row["_engine"] for row in rows} == {"google", "bing", "yandex"}


def test_quality_search_promotes_cross_engine_consensus(monkeypatch) -> None:
    class FakeResult:
        def __init__(self, url: str) -> None:
            self.title = url
            self.href = url
            self.body = "body"

    rows_by_engine = {
        "google": [FakeResult("https://google-only.example"), FakeResult("https://consensus.example")],
        "brave": [FakeResult("https://brave-only.example"), FakeResult("https://consensus.example")],
        "bing": [FakeResult("https://bing-only.example")],
    }

    class FakeEngine:
        def __init__(self, name: str) -> None:
            self.name = name

        def search(self, *_args, **_kwargs):
            return rows_by_engine[self.name]

    monkeypatch.setattr(ROUTING_STATE, "plan", lambda *_args, **_kwargs: ["google", "brave", "bing"])
    monkeypatch.setattr(ROUTING_STATE, "record", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(DDGS, "_engine", lambda _self, name, _timeout: FakeEngine(name))

    rows = DDGS(timeout=10).text(
        "query",
        backend="auto",
        max_results=10,
        max_attempts=3,
        routing_profile="quality",
    )

    assert rows[0]["href"] == "https://consensus.example"
    assert rows[0]["_votes"] == 2


def test_quality_search_runs_at_most_two_engines_in_parallel(monkeypatch) -> None:
    lock = threading.Lock()
    active = 0
    max_active = 0
    throttle_inputs: list[set[str]] = []

    class FakeResult:
        title = "result"
        body = "body"

        def __init__(self, name: str) -> None:
            self.href = f"https://{name}.example/result"

    class FakeEngine:
        def __init__(self, name: str) -> None:
            self.name = name

        def search(self, *_args, **_kwargs):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.03)
            with lock:
                active -= 1
            return [FakeResult(self.name)]

    monkeypatch.setattr(ROUTING_STATE, "plan", lambda *_args, **_kwargs: ["google", "brave", "bing", "yandex"])
    monkeypatch.setattr(ROUTING_STATE, "record", lambda *_args, **_kwargs: None)
    def fake_quality_concurrency(available):
        throttle_inputs.append(available)
        return 2

    monkeypatch.setattr(ROUTING_STATE, "quality_concurrency", fake_quality_concurrency)
    monkeypatch.setattr(DDGS, "_engine", lambda _self, name, _timeout: FakeEngine(name))

    DDGS(timeout=10).text("query", backend="auto", max_results=10, max_attempts=4, routing_profile="quality")

    assert max_active == 2
    assert all({"google", "brave"} <= available for available in throttle_inputs)


def test_quality_search_obeys_timeout_throttle(monkeypatch) -> None:
    lock = threading.Lock()
    active = 0
    max_active = 0

    class FakeResult:
        title = "result"
        body = "body"

        def __init__(self, name: str) -> None:
            self.href = f"https://{name}.example/result"

    class FakeEngine:
        def __init__(self, name: str) -> None:
            self.name = name

        def search(self, *_args, **_kwargs):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.01)
            with lock:
                active -= 1
            return [FakeResult(self.name)]

    monkeypatch.setattr(ROUTING_STATE, "plan", lambda *_args, **_kwargs: ["google", "brave"])
    monkeypatch.setattr(ROUTING_STATE, "record", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ROUTING_STATE, "quality_concurrency", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(DDGS, "_engine", lambda _self, name, _timeout: FakeEngine(name))

    DDGS(timeout=10).text("query", backend="auto", max_results=10, max_attempts=2, routing_profile="quality")

    assert max_active == 1
