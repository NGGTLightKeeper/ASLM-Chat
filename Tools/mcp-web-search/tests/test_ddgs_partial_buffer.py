import asyncio
import json
import shutil
import sys
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.fetch import ddgs_client
from core.models.search import SearchResult
from core.config import load_search_config
from services.web_search import (
    WebSearchService,
    _build_effort_options,
    _get_output_profile,
)


def _workspace_tmp_dir() -> Path:
    path = ROOT / "tmp" / f"pytest_partial_buffer_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _result(url: str, title: str = "Title", snippet: str = "Snippet") -> SearchResult:
    return SearchResult(
        url=url,
        title=title,
        snippet=snippet,
        engine="ddgs:test",
        method_hint="synthetic",
    )


def test_partial_buffer_merges_and_dedupes_by_url() -> None:
    tmp_dir = _workspace_tmp_dir()
    try:
        buffer_path = tmp_dir / "partial.json"

        ddgs_client._write_partial_results(
            str(buffer_path),
            [
                _result("https://example.com/a", "A1"),
                _result("https://example.com/b", "B"),
            ],
        )
        ddgs_client._write_partial_results(
            str(buffer_path),
            [
                _result("https://example.com/a", "A2"),
                _result("https://example.com/c", "C"),
            ],
        )

        payload = json.loads(buffer_path.read_text(encoding="utf-8"))
        assert payload["partial"] is True
        assert [item["url"] for item in payload["results"]] == [
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/c",
        ]
        assert payload["results"][0]["title"] == "A1"

        restored = ddgs_client._read_partial_results(str(buffer_path))
        assert [item.url for item in restored] == [
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/c",
        ]
        assert all("partial_timeout" in item.method_hint for item in restored)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_partial_buffer_read_is_safe_for_missing_or_invalid_files() -> None:
    tmp_dir = _workspace_tmp_dir()
    try:
        missing = tmp_dir / "missing.json"
        broken = tmp_dir / "broken.json"
        broken.write_text("{ not json", encoding="utf-8")

        assert ddgs_client._read_partial_results(str(missing)) == []
        assert ddgs_client._read_partial_results(str(broken)) == []
        assert ddgs_client._read_partial_results(None) == []
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_async_ddgs_search_returns_partial_results_on_worker_timeout(monkeypatch) -> None:
    captured_paths: list[str] = []

    class FakeProcess:
        returncode = None

        async def communicate(self, stdin: bytes) -> tuple[bytes, bytes]:
            payload = json.loads(stdin.decode("utf-8"))
            buffer_path = payload["partial_buffer_path"]
            captured_paths.append(buffer_path)
            ddgs_client._write_partial_results(
                buffer_path,
                [
                    _result("https://example.com/partial-1", "Partial 1"),
                    _result("https://example.com/partial-2", "Partial 2"),
                ],
            )
            await asyncio.sleep(1.0)
            return b"", b""

        def kill(self) -> None:
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode or -9

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return FakeProcess()

    monkeypatch.setattr(ddgs_client.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(ddgs_client, "DDGS_USE_SUBPROCESS", True)
    monkeypatch.setattr(ddgs_client, "_WORKER_SCRIPT", ROOT / "core" / "fetch" / "_ddgs_worker.py")

    results = asyncio.run(
        ddgs_client.async_ddgs_search(
            "synthetic timeout",
            max_results=5,
            worker_timeout=0.05,
            use_subprocess=True,
        )
    )

    assert [item.url for item in results] == [
        "https://example.com/partial-1",
        "https://example.com/partial-2",
    ]
    assert all("partial_timeout" in item.method_hint for item in results)
    assert len(captured_paths) == 1
    assert not Path(captured_paths[0]).exists()
    assert not Path(captured_paths[0] + ".tmp").exists()


def test_async_ddgs_search_uses_one_buffer_per_request(monkeypatch) -> None:
    captured_paths: list[str] = []

    class FakeProcess:
        returncode = None

        async def communicate(self, stdin: bytes) -> tuple[bytes, bytes]:
            payload = json.loads(stdin.decode("utf-8"))
            buffer_path = payload["partial_buffer_path"]
            captured_paths.append(buffer_path)
            ddgs_client._write_partial_results(
                buffer_path,
                [_result(f"https://example.com/{len(captured_paths)}")],
            )
            await asyncio.sleep(1.0)
            return b"", b""

        def kill(self) -> None:
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode or -9

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return FakeProcess()

    monkeypatch.setattr(ddgs_client.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(ddgs_client, "DDGS_USE_SUBPROCESS", True)
    monkeypatch.setattr(ddgs_client, "_WORKER_SCRIPT", ROOT / "core" / "fetch" / "_ddgs_worker.py")

    first = asyncio.run(
        ddgs_client.async_ddgs_search("first synthetic timeout", worker_timeout=0.05, use_subprocess=True)
    )
    second = asyncio.run(
        ddgs_client.async_ddgs_search("second synthetic timeout", worker_timeout=0.05, use_subprocess=True)
    )

    assert [item.url for item in first] == ["https://example.com/1"]
    assert [item.url for item in second] == ["https://example.com/2"]
    assert len(captured_paths) == 2
    assert captured_paths[0] != captured_paths[1]
    assert all(not Path(path).exists() for path in captured_paths)


def test_zero_result_high_fallback_uses_bounded_snippet_only_options(monkeypatch) -> None:
    calls = []

    async def fake_pipeline(
        self,
        query,
        lang,
        query_types,
        query_type,
        out_profile,
        opts,
        req_id="-",
        **_kwargs,
    ):
        calls.append(
            {
                "query": query,
                "effort": opts.effort,
                "fetch_previews": opts.fetch_previews,
                "candidate_pool_multiplier": opts.candidate_pool_multiplier,
                "ddgs_worker_timeout": opts.ddgs_worker_timeout,
                "ddgs_engine_timeout": opts.ddgs_engine_timeout,
                "ddgs_max_retries": opts.ddgs_max_retries,
                "use_fast_academic": opts.use_fast_academic,
                "max_results": opts.max_results,
                "profile_max_results": out_profile.max_results,
            }
        )
        if len(calls) == 1:
            return [], []
        return [_result("https://example.com/fallback", "Fallback")], []

    monkeypatch.setattr(WebSearchService, "_run_search_pipeline", fake_pipeline)

    cfg = load_search_config()
    opts = _build_effort_options(cfg, effort="high", max_results=10, fetch_previews=True, timelimit=None)
    query_types = ["technical"]
    service = WebSearchService(options=opts)

    results, _triage, effective_query = asyncio.run(
        service._run_with_zero_result_fallback(
            provider_query="Python 3.14.0 alpha 6 changelog free-threading JIT improvements",
            analysis_query="Python 3.14.0 alpha 6 changelog free-threading JIT improvements",
            query_types=query_types,
            out_profile=_get_output_profile(query_types),
            opts=opts,
            req_id="test",
        )
    )

    assert [item.url for item in results] == ["https://example.com/fallback"]
    assert effective_query
    assert calls[0]["effort"] == "high"
    assert calls[0]["fetch_previews"] is True
    assert calls[0]["candidate_pool_multiplier"] > 1

    fallback = calls[1]
    assert fallback["effort"] == "medium"
    assert fallback["fetch_previews"] is False
    assert fallback["candidate_pool_multiplier"] == 1
    assert fallback["ddgs_worker_timeout"] <= 8.0
    assert fallback["ddgs_engine_timeout"] <= 5
    assert fallback["ddgs_max_retries"] == 1
    assert fallback["use_fast_academic"] is False
    assert fallback["max_results"] <= 10


def test_zero_result_high_fallback_does_not_repeat_full_high_for_every_variant(monkeypatch) -> None:
    fallback_calls = []

    async def fake_pipeline(
        self,
        query,
        lang,
        query_types,
        query_type,
        out_profile,
        opts,
        req_id="-",
        **_kwargs,
    ):
        fallback_calls.append((query, opts.effort, opts.fetch_previews, opts.ddgs_worker_timeout))
        return [], []

    monkeypatch.setattr(WebSearchService, "_run_search_pipeline", fake_pipeline)

    cfg = load_search_config()
    opts = _build_effort_options(cfg, effort="high", max_results=10, fetch_previews=True, timelimit=None)
    query = '"Python 3.14.0 alpha 6" changelog free-threading JIT improvements'
    query_types = ["technical"]
    service = WebSearchService(options=opts)

    results, _triage, _effective_query = asyncio.run(
        service._run_with_zero_result_fallback(
            provider_query=query,
            analysis_query=query,
            query_types=query_types,
            out_profile=_get_output_profile(query_types),
            opts=opts,
            req_id="test",
        )
    )

    assert results == []
    assert len(fallback_calls) == 1 + len(WebSearchService._fallback_query_variants(query))
    assert fallback_calls[0][1] == "high"
    for _query, effort, fetch_previews, worker_timeout in fallback_calls[1:]:
        assert effort == "medium"
        assert fetch_previews is False
        assert worker_timeout <= 8.0
