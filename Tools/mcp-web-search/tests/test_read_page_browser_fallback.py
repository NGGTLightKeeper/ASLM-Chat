# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import core.config as config_module
import core.fetch.onion as onion_module
from core.fetch.browser.models import BrowserFetch, STATUS_OK
from core.fetch.onion.transport import OnionFetch
from core.profiles import METHOD_BROWSER, METHOD_HTTPX
from core.read import service as read_service
from custom_domains import GenericRequest


class _Cache:
    def get_cached(self, _key):
        return None

    def is_fresh(self, _key):
        return False

    def cache_page(self, *_args, **_kwargs):
        return None


class _Profiles:
    def __init__(self):
        self.attempts = []

    def record(self, url, attempt):
        self.attempts.append((url, attempt))

    def record_reputation(self, *_args, **_kwargs):
        return None


def _service() -> read_service.ReadPageService:
    service = read_service.ReadPageService.__new__(read_service.ReadPageService)
    service._cfg = SimpleNamespace(extraction=SimpleNamespace(min_content_length=40))
    service._opts = read_service.ReadPageOptions(timeout=5, max_chars=20_000, allow_browser=True)
    service._cache = _Cache()
    service._profiles = _Profiles()
    service._resolve_strategy = lambda _url, _req: (False, None, False)
    return service


def test_empty_http_response_retries_through_browser(monkeypatch):
    service = _service()
    calls = []

    async def fetch_candidate(_url, **_kwargs):
        return read_service.RawFetch(None, METHOD_HTTPX, status=402), None

    async def browser_ok():
        return True

    async def fetch_browser(url, _timeout):
        calls.append(url)
        html = "<html><body>browser content</body></html>"
        result = BrowserFetch(url=url, status=STATUS_OK, html=html, engine="chromium")
        return read_service.RawFetch(html, METHOD_BROWSER, "chromium", 200), result

    service._fetch_candidate = fetch_candidate
    service._browser_ok = browser_ok
    monkeypatch.setattr(read_service, "_fetch_browser", fetch_browser)
    monkeypatch.setattr(read_service, "normalize_page", lambda _url, _html: "B" * 100)

    result = asyncio.run(service._generic_read(GenericRequest(url="https://example.com/page")))

    assert result.ok is True
    assert result.method == METHOD_BROWSER
    assert result.markdown == "B" * 100
    assert calls == ["https://example.com/page"]


def test_empty_browser_first_response_is_not_retried(monkeypatch):
    service = _service()
    browser_calls = []

    async def fetch_candidate(_url, **_kwargs):
        return read_service.RawFetch(None, METHOD_BROWSER, "chromium", 0), None

    async def browser_ok():
        return True

    async def fetch_browser(_url, _timeout):
        browser_calls.append(_url)
        raise AssertionError("browser fallback must not run twice")

    service._fetch_candidate = fetch_candidate
    service._browser_ok = browser_ok
    monkeypatch.setattr(read_service, "_fetch_browser", fetch_browser)

    result = asyncio.run(service._generic_read(GenericRequest(url="https://example.com/page")))

    assert result.ok is False
    assert browser_calls == []


def test_failed_browser_fallback_keeps_original_http_status(monkeypatch):
    service = _service()

    async def fetch_candidate(_url, **_kwargs):
        return read_service.RawFetch(None, METHOD_HTTPX, status=402), None

    async def browser_ok():
        return True

    async def fetch_browser(url, _timeout):
        return read_service.RawFetch(None, METHOD_BROWSER, "chromium", 0), None

    service._fetch_candidate = fetch_candidate
    service._browser_ok = browser_ok
    monkeypatch.setattr(read_service, "_fetch_browser", fetch_browser)

    result = asyncio.run(service._generic_read(GenericRequest(url="https://example.com/page")))

    assert result.ok is False
    assert result.markdown.endswith("(HTTP 402)")


# Preserve short but valid Onion content instead of treating the quality threshold as emptiness.
def test_short_onion_page_remains_a_success(monkeypatch):
    service = _service()
    service._cfg = SimpleNamespace(extraction=SimpleNamespace(min_content_length=800))
    short_markdown = "# Short Onion page\n\n**Site:** example.onion\n\n---\n\nUseful short content."

    # Return a successful Onion response without opening a real Tor connection.
    async def fetch_onion(url, **_kwargs):
        return OnionFetch(
            url=url,
            status="ok",
            ok=True,
            http_status=200,
            text="<p>Useful short content.</p>",
        )

    monkeypatch.setattr(
        config_module,
        "load_search_config",
        lambda: SimpleNamespace(tor=SimpleNamespace(enabled=True)),
    )
    monkeypatch.setattr(onion_module, "onion_fetch", fetch_onion)
    monkeypatch.setattr(
        read_service,
        "normalize_page",
        lambda _url, _html, **_kwargs: short_markdown,
    )

    result = asyncio.run(service._read_onion("http://example.onion/page"))

    assert result.ok is True
    assert result.method == "onion"
    assert "Very little content extracted" in result.markdown
    assert "Useful short content" in result.markdown
