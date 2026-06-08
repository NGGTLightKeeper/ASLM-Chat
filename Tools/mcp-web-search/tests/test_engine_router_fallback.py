import time

from core.fetch import ddgs_client
from core.fetch.engine_router import EngineRouter
from core.fetch.engine_stats import BACKUP_ENGINES, PRIMARY_ENGINES, make_registry
from core.ddgs.engines import ENGINES
from core.models.search import SearchResult


def test_ddgs_client_uses_vendored_search_core() -> None:
    assert ddgs_client._DDGS_AVAILABLE is True
    assert ddgs_client.DDGS.__module__ == "core.ddgs"


def test_router_backends_exist_in_vendored_search_core() -> None:
    assert set(PRIMARY_ENGINES + BACKUP_ENGINES) <= set(ENGINES["text"])


def test_router_keeps_backup_engines_out_of_primary_pool() -> None:
    router = EngineRouter(make_registry())

    assert set(router.pick_pool(10)) == set(PRIMARY_ENGINES)
    assert set(router.pick_backup_pool(10)) == set(BACKUP_ENGINES)
    assert router.pick() in PRIMARY_ENGINES
    assert "wikipedia" not in router.registry


def test_empty_primary_immediately_hot_swaps_to_backup(monkeypatch) -> None:
    calls: list[str] = []

    def fake_search(self, query, max_results=10, backend="auto", **_kwargs):
        calls.append(backend)
        if backend == "startpage":
            return [
                SearchResult(
                    url="https://example.com/result",
                    title="Result",
                    snippet="A useful result with a non-trivial snippet.",
                    engine="ddgs:startpage",
                )
            ]
        return []

    monkeypatch.setattr(ddgs_client.DDGSClient, "search_to_results", fake_search)
    client = ddgs_client.DDGSClient(timeout=2, max_retries=2, request_delay=(0.0, 0.0))

    started = time.perf_counter()
    results = client.search_with_fallback(
        "specialized query",
        max_results=5,
        query_type="technical",
        query_types=["technical"],
        hedge_count=1,
    )

    assert [result.engine for result in results] == ["ddgs:startpage"]
    assert calls[:2] == ["google", "startpage"]
    assert time.perf_counter() - started < 1.0


def test_slow_primary_starts_backup_without_waiting_for_engine_timeout(monkeypatch) -> None:
    calls: list[str] = []

    def fake_search(self, query, max_results=10, backend="auto", **_kwargs):
        calls.append(backend)
        if backend == "google":
            time.sleep(0.3)
            return []
        if backend == "startpage":
            return [
                SearchResult(
                    url="https://example.com/backup",
                    title="Backup result",
                    snippet="A useful result returned before the primary timeout.",
                    engine="ddgs:startpage",
                )
            ]
        return []

    monkeypatch.setattr(ddgs_client, "BACKUP_HEDGE_DELAY", 0.02)
    monkeypatch.setattr(ddgs_client.DDGSClient, "search_to_results", fake_search)
    client = ddgs_client.DDGSClient(timeout=1, max_retries=1, request_delay=(0.0, 0.0))

    started = time.perf_counter()
    results = client.search_with_fallback(
        "slow specialized query",
        max_results=5,
        query_type="technical",
        query_types=["technical"],
        hedge_count=1,
    )

    assert [result.engine for result in results] == ["ddgs:startpage"]
    assert calls[:2] == ["google", "startpage"]
    assert time.perf_counter() - started < 0.2


def test_fallback_paths_never_use_ddgs_auto_or_aggregate_backends() -> None:
    assert "auto" not in ddgs_client.BACKEND_FALLBACK
    assert "auto" not in ddgs_client.BACKEND_SITE_QUERY
    assert all("," not in backend for backend in ddgs_client.BACKEND_FALLBACK)
    assert all("," not in backend for backend in ddgs_client.BACKEND_SITE_QUERY)
