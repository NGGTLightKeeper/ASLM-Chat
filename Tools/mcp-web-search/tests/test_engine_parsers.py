from __future__ import annotations

import pytest

from core.ddgs.engines.bing import Bing
from core.ddgs.engines.bing_news import BingNews
from core.ddgs.engines.brave import Brave
from core.ddgs.engines.brave_news import BraveNews
from core.ddgs.engines.google import Google
from core.ddgs.engines.startpage import Startpage
from core.ddgs.exceptions import DDGSException
from core.ddgs.results import TextResult


def test_google_payload_separates_duplicate_filter_from_safesearch() -> None:
    payload = Google(timeout=5).build_payload("query", "us-en", "moderate", None)

    assert payload["filter"] == "0"
    assert payload["safe"] == "medium"
    assert payload["gl"] == "US"
    assert payload["ie"] == payload["oe"] == "utf8"


def test_google_detects_short_captcha_page() -> None:
    engine = Google(timeout=5)

    with pytest.raises(DDGSException, match="captcha"):
        engine.pre_process_html("<html>Our systems detected unusual traffic. /sorry/</html>")


def test_brave_discards_partial_and_internal_ad_links() -> None:
    results = [
        TextResult(title="Good", href="https://example.com/page", body="body"),
        TextResult(title="Partial", href="/search?q=ad", body="body"),
        TextResult(title="", href="https://example.com/no-title", body="body"),
    ]

    output = Brave.post_extract_results(None, results)

    assert [result.href for result in output] == ["https://example.com/page"]


def test_bing_parser_removes_decorative_icon_text() -> None:
    html = """
    <ol id="b_results">
      <li class="b_algo">
        <h2><a href="https://example.com">Example</a></h2>
        <div class="b_caption"><p><span class="algoSlug_icon">ICON</span>Useful snippet</p></div>
      </li>
    </ol>
    """

    output = Bing(timeout=5).extract_results(html)

    assert output[0].body == "Useful snippet"


def test_startpage_reuses_form_token(monkeypatch) -> None:
    Startpage._sc_code = ""
    Startpage._sc_expires_at = 0.0
    calls = 0

    class Response:
        text = '<form id="search"><input name="sc" value="token-1"></form>'

    engine = Startpage(timeout=5)

    def fake_request(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return Response()

    monkeypatch.setattr(engine.http_client, "request", fake_request)

    assert engine.get_sc() == "token-1"
    assert engine.get_sc() == "token-1"
    assert calls == 1


def test_startpage_reports_missing_token_as_failure(monkeypatch) -> None:
    Startpage._sc_code = ""
    Startpage._sc_expires_at = 0.0

    class Response:
        text = "<html></html>"

    engine = Startpage(timeout=5)
    monkeypatch.setattr(engine.http_client, "request", lambda *_args, **_kwargs: Response())

    with pytest.raises(DDGSException, match="token missing"):
        engine.get_sc()


def test_specialized_news_engines_parse_news_cards() -> None:
    brave_html = """
    <div data-type="news">
      <a class="result-header" href="https://news.example/brave"><span class="snippet-title">Brave title</span></a>
      <p class="desc">Brave description</p>
    </div>
    """
    bing_html = """
    <div class="newsitem">
      <a class="title" href="https://news.example/bing">Bing title</a>
      <div class="snippet">Bing description</div>
    </div>
    """

    brave = BraveNews(timeout=5).post_extract_results(BraveNews(timeout=5).extract_results(brave_html))
    bing = BingNews(timeout=5).post_extract_results(BingNews(timeout=5).extract_results(bing_html))

    assert brave[0].href == "https://news.example/brave"
    assert brave[0].body == "Brave description"
    assert bing[0].href == "https://news.example/bing"
    assert bing[0].body == "Bing description"
