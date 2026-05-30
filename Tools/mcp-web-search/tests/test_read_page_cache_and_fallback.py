import asyncio
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]

from core.cache.source_cache import SourceCache
from services import read_page as read_page_module
from services.read_page import (
    ReadPageOptions,
    ReadPageService,
    _READ_PAGE_STRATEGY_VERSION,
    _cache_key_for_read,
)


def _workspace_tmp_dir() -> Path:
    path = ROOT / "tmp" / f"pytest_read_page_cache_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _html(body: str = "Cached page body") -> str:
    paragraphs = "".join(f"<p>{body} paragraph {i}</p>" for i in range(80))
    return (
        "<html><head><title>Cache Test</title></head>"
        f"<body><main><h1>Cache Test</h1>{paragraphs}</main></body></html>"
    )


def test_source_cache_round_trips_and_searches_cached_pages() -> None:
    tmp_dir = _workspace_tmp_dir()
    cache = None
    try:
        cache = SourceCache(str(tmp_dir / "source_cache.db"))
        url = "https://example.com/cache-round-trip"
        cache.cache_page(url, "Cache Title", "alpha beta cache body", "<html>raw</html>")

        cached = cache.get_cached(url)
        assert cached is not None
        assert cached.title == "Cache Title"
        assert cached.clean_text == "alpha beta cache body"
        assert cached.raw_html == "<html>raw</html>"
        assert cache.is_fresh(url)
        assert cache.page_count() == 1

        results = cache.search_local("alpha beta", limit=5)
        assert [item.url for item in results] == ["https://example.com/cache-round-trip"]
    finally:
        if cache is not None:
            cache._close_thread_conn()
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_source_cache_recovers_corrupt_database_and_keeps_working() -> None:
    tmp_dir = _workspace_tmp_dir()
    cache = None
    try:
        db_path = tmp_dir / "source_cache.db"
        db_path.write_bytes(b"not sqlite")

        cache = SourceCache(str(db_path))
        assert cache.page_count() == 0
        assert list(tmp_dir.glob("source_cache.db.corrupt-*"))

        url = "https://example.com/after-recovery"
        cache.cache_page(url, "Recovered", "fresh cache text", "<html>fresh</html>")
        cached = cache.get_cached(url)
        assert cached is not None
        assert cached.raw_html == "<html>fresh</html>"
        assert cache.is_fresh(url)
    finally:
        if cache is not None:
            cache._close_thread_conn()
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_read_page_uses_fresh_cache_without_network_or_camoufox(monkeypatch) -> None:
    tmp_dir = _workspace_tmp_dir()
    cache = None
    try:
        cache = SourceCache(str(tmp_dir / "source_cache.db"))
        monkeypatch.setattr(read_page_module, "_cache", cache)

        url = "https://example.com/cached-read"
        cache_key = _cache_key_for_read(
            url,
            strategy_tag=_READ_PAGE_STRATEGY_VERSION,
            variant="default",
        )
        cache.cache_page(cache_key, "", clean_text="", raw_html=_html("served from sqlite cache"))

        async def fail_fetch(*_args, **_kwargs):
            raise AssertionError("network/Camoufox fetch should not run on a fresh cache hit")

        monkeypatch.setattr(ReadPageService, "_fetch_raw_html", fail_fetch)

        service = ReadPageService(ReadPageOptions(timeout=1.0, max_chars=20_000))
        text, attempts = asyncio.run(service.read_with_trace(url))

        assert "Cache Test" in text
        assert attempts
        assert attempts[0].fetch_method == "cache"
    finally:
        if cache is not None:
            cache._close_thread_conn()
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_fetch_raw_html_keeps_camoufox_idle_when_network_succeeds(monkeypatch) -> None:
    service = ReadPageService(ReadPageOptions(timeout=1.0))
    calls = {"network": 0, "camoufox": 0}

    async def fake_fetch_race(*_args, **_kwargs):
        calls["network"] += 1
        return "<html>network html</html>"

    async def fake_camoufox(*_args, **_kwargs):
        calls["camoufox"] += 1
        raise AssertionError("Camoufox should stay idle when network fetch succeeds")

    monkeypatch.setattr(read_page_module, "_fetch_race", fake_fetch_race)
    monkeypatch.setattr(read_page_module, "fetch_with_camoufox", fake_camoufox)

    html = asyncio.run(
        service._fetch_raw_html("https://example.com/network-ok", service._opts, "https://example.com/network-ok")
    )

    assert html == "<html>network html</html>"
    assert calls == {"network": 1, "camoufox": 0}


def test_fetch_raw_html_falls_back_to_camoufox_after_empty_network(monkeypatch) -> None:
    service = ReadPageService(ReadPageOptions(timeout=1.0))
    calls = {"network": 0, "camoufox": 0}

    async def fake_fetch_race(*_args, **_kwargs):
        calls["network"] += 1
        return None

    async def fake_camoufox(*_args, **_kwargs):
        calls["camoufox"] += 1
        return SimpleNamespace(success=True, html="<html>browser html</html>", error=None)

    monkeypatch.setattr(read_page_module, "_fetch_race", fake_fetch_race)
    monkeypatch.setattr(read_page_module, "fetch_with_camoufox", fake_camoufox)

    html = asyncio.run(
        service._fetch_raw_html("https://example.com/network-empty", service._opts, "https://example.com/network-empty")
    )

    assert html == "<html>browser html</html>"
    assert calls == {"network": 1, "camoufox": 1}
