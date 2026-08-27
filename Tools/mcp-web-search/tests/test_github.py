# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from custom_domains.base import FetchContext, PageResult
from custom_domains import github


def _context(generic_read):
    return FetchContext(
        timeout=10,
        max_chars=10000,
        focus="",
        cfg=SimpleNamespace(),
        cache=None,
        generic_read=generic_read,
    )


def test_github_handler_falls_back_to_html_on_api_rate_limit(monkeypatch):
    async def api_failure(_url, timeout=20.0):
        return "Error: GitHub API repo fetch failed: 403 rate limit exceeded for api.github.com"

    async def html_success(request):
        assert request.url == "https://github.com/openai/codex"
        return PageResult(markdown="# openai/codex\nHTML content", ok=True, method="basic")

    monkeypatch.setattr(github, "fetch_github_page", api_failure)

    result = asyncio.run(github.HANDLER.read(
        "https://github.com/openai/codex",
        _context(html_success),
    ))

    assert result.ok is True
    assert result.method == "github_html_fallback"
    assert "HTML content" in result.markdown


def test_github_handler_keeps_non_rate_limit_api_error(monkeypatch):
    fallback_called = False

    async def api_failure(_url, timeout=20.0):
        return "Error: GitHub API repo fetch failed: 404 Not Found"

    async def html_fallback(_request):
        nonlocal fallback_called
        fallback_called = True
        return PageResult(markdown="unexpected", ok=True)

    monkeypatch.setattr(github, "fetch_github_page", api_failure)

    result = asyncio.run(github.HANDLER.read(
        "https://github.com/openai/missing",
        _context(html_fallback),
    ))

    assert result.ok is False
    assert fallback_called is False

