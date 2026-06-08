import time

from core.ddgs.ddgs import DDGS
from core.ddgs.engines import ENGINES
from core.ddgs.routing import PROFILES, ROUTING_STATE, HealthState, RoutingState, infer_language
from core.fetch import ddgs_client
from core.fetch.engine_stats import BACKUP_ENGINES, PRIMARY_ENGINES


def test_ddgs_client_uses_vendored_search_core() -> None:
    assert ddgs_client._DDGS_AVAILABLE is True
    assert ddgs_client.DDGS.__module__ == "core.ddgs"


def test_router_backends_exist_in_vendored_search_core() -> None:
    assert set(PRIMARY_ENGINES + BACKUP_ENGINES) <= set(ENGINES["text"])


def test_provider_family_links_are_explicit() -> None:
    assert PROFILES["duckduckgo"].provider == PROFILES["yahoo"].provider == "bing"
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
