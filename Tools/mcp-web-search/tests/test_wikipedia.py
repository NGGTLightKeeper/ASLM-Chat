# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import custom_domains
import custom_domains.wikipedia as wikipedia


def test_wikipedia_article_urls_map_to_their_language_api():
    endpoint, params = wikipedia._api_request(
        "https://ru.wikipedia.org/wiki/Python_(язык_программирования)#История"
    )

    assert endpoint == "https://ru.wikipedia.org/w/api.php"
    assert params["page"] == "Python_(язык_программирования)"
    assert params["redirects"] == "1"


def test_mobile_and_revision_urls_are_supported():
    endpoint, params = wikipedia._api_request(
        "https://en.m.wikipedia.org/w/index.php?title=Python&oldid=12345"
    )

    assert endpoint == "https://en.wikipedia.org/w/api.php"
    assert params["oldid"] == "12345"
    assert "page" not in params


def test_non_article_and_lookalike_urls_do_not_match():
    assert wikipedia._api_request("https://www.wikipedia.org/") is None
    assert wikipedia._api_request("https://en.wikipedia.org/") is None
    assert wikipedia._api_request("https://en.wikipedia.org.evil.test/wiki/Python") is None


def test_payload_normalization_keeps_lead_headings_and_links():
    payload = {
        "parse": {
            "title": "Example article",
            "text": (
                '<div class="mw-parser-output">'
                '<p>Lead paragraph with <a href="/wiki/Useful">a useful link</a>. '
                + "Substantial article prose remains in the API output. " * 8
                + "</p>"
                '<h2>History</h2><p>Historical details remain available.</p>'
                "</div>"
            ),
        }
    }

    markdown = wikipedia._payload_to_markdown(
        "https://en.wikipedia.org/wiki/Example_article", payload
    )

    assert markdown.startswith("# Example article")
    assert "Lead paragraph" in markdown
    assert "## History" in markdown
    assert "[a useful link](https://en.wikipedia.org/wiki/Useful)" in markdown


def test_api_title_overrides_an_html_section_selected_as_document_title():
    payload = {
        "parse": {
            "title": "Canonical API title",
            "text": "<h2>Misleading section</h2><p>" + "Article body. " * 30 + "</p>",
        }
    }

    markdown = wikipedia._payload_to_markdown(
        "https://en.wikipedia.org/wiki/Canonical_API_title", payload
    )

    assert markdown.startswith("# Canonical API title\n")


def test_handler_uses_api_result_and_requests_budget(monkeypatch):
    async def fake_fetch(url: str, timeout: float = 20.0) -> str:
        assert timeout == 7.0
        return "# Article\n\nAPI content"

    monkeypatch.setattr(wikipedia, "fetch_wikipedia_page", fake_fetch)
    ctx = SimpleNamespace(timeout=7.0)
    result = asyncio.run(
        wikipedia.HANDLER.read("https://en.wikipedia.org/wiki/Article", ctx)
    )

    assert result.ok
    assert result.method == "wikipedia_api"
    assert result.apply_budget


def test_wikipedia_handler_is_registered():
    handler = custom_domains.match("https://de.wikipedia.org/wiki/Python")

    assert handler is wikipedia.HANDLER
