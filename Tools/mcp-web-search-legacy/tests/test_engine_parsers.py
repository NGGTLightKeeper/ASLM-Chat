from __future__ import annotations

import pytest

from core.ddgs.engines.brave import Brave
from core.ddgs.engines.brave_news import BraveNews
from core.ddgs.engines.google import Google
from core.ddgs.engines.qwant import Qwant
from core.ddgs.engines.startpage import Startpage
from core.ddgs.engines.stackoverflow import StackOverflow
from core.ddgs.engines.yep import Yep
from core.ddgs.exceptions import DDGSException, RatelimitException
from core.ddgs.results import TextResult


def test_google_payload_separates_duplicate_filter_from_safesearch() -> None:
    payload = Google(timeout=5).build_payload("query", "us-en", "moderate", None)

    assert payload["filter"] == "0"
    assert payload["safe"] == "medium"
    assert payload["gl"] == "US"
    assert payload["ie"] == payload["oe"] == "utf8"
    assert payload["gbv"] == "1"


def test_google_desktop_xpath_parses_basic_serp() -> None:
    html = """
    <html><body>
      <a href="/url?q=https%3A%2F%2Fwww.python.org%2F&amp;sa=U">
        <h3>Welcome to Python.org</h3>
        <div class="VwiC3b">The official home of the Python Programming Language.</div>
      </a>
      <a href="https://www.google.com/search?q=python"><h3>More</h3></a>
    </body></html>
    """
    engine = Google(timeout=5)
    results = engine.post_extract_results(engine.extract_results(html))

    assert len(results) == 1
    assert results[0].title == "Welcome to Python.org"
    assert results[0].href == "https://www.python.org/"


def test_google_post_extract_unwraps_redirect_links() -> None:
    results = [
        TextResult(
            title="Example",
            href="/url?q=https%3A%2F%2Fexample.com%2Fpage&sa=U",
            body="snippet",
        ),
        TextResult(title="Internal", href="https://www.google.com/search?q=x", body=""),
    ]

    output = Google.post_extract_results(None, results)

    assert len(output) == 1
    assert output[0].href == "https://example.com/page"


def test_google_accepts_consent_page_before_parsing() -> None:
    consent_html = """
    <html><body>
      <title>Before you continue to Google Search</title>
      <form action="https://consent.google.com/save" method="POST">
        <input type="hidden" name="continue" value="https://www.google.com/search?q=python">
        <input type="hidden" name="set_sc" value="true">
        <input type="hidden" name="set_aps" value="true">
      </form>
    </body></html>
    """
    serp_html = """
    <html><body>
      <a href="/url?q=https%3A%2F%2Fexample.com%2F&amp;sa=U">
        <h3>Example</h3>
      </a>
    </body></html>
  """
    engine = Google(timeout=5)
    calls: list[tuple[str, str]] = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url))
        if method == "GET" and "google.com/search" in url:
            return consent_html
        if method == "POST" and "consent.google.com/save" in url:
            return serp_html
        if method == "GET" and url == "https://www.google.com/search?q=python":
            return serp_html
        return ""

    engine.request = fake_request  # type: ignore[method-assign]
    engine.http_client.request = lambda method, url, **kwargs: type(  # type: ignore[method-assign]
        "Resp", (), {"status_code": 200, "text": fake_request(method, url, **kwargs)}
    )()

    results = engine.search("python", region="us-en", safesearch="moderate", timelimit=None, page=1) or []

    assert [call[0] for call in calls] == ["GET", "POST"]
    assert len(results) == 1
    assert results[0].href == "https://example.com/"


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


def test_startpage_discards_relative_tracking_links() -> None:
    output = Startpage.post_extract_results(None, [
        TextResult(title="Good", href="https://example.com/page", body="body"),
        TextResult(title="Tracking", href="/sp/click?foo=bar", body="body"),
    ])

    assert [result.href for result in output] == ["https://example.com/page"]


def test_stackoverflow_api_parser_returns_question_metadata() -> None:
    output = StackOverflow(timeout=5).extract_results(
        '{"items":[{"title":"Why SSI aborts?","link":"https://stackoverflow.com/q/1",'
        '"tags":["postgresql"],"score":12,"answer_count":3,"is_answered":true}]}'
    )

    assert output[0].href == "https://stackoverflow.com/q/1"
    assert "3 answers" in output[0].body


def test_stackoverflow_payload_uses_string_query_params() -> None:
    payload = StackOverflow(timeout=5).build_payload(
        "python asyncio timeout", "us-en", "moderate", None, page=2,
    )

    assert payload["page"] == "2"
    assert payload["pagesize"] == "10"


def test_stackoverflow_reports_ip_block_as_rate_limit(monkeypatch) -> None:
    class Response:
        status_code = 400
        text = "<h1>Too many requests</h1><p>This IP has been temporarily rate limited.</p>"

        @staticmethod
        def raise_for_status() -> None:
            raise AssertionError("rate limit should be detected before generic HTTP handling")

    monkeypatch.setattr(
        "curl_cffi.requests.get",
        lambda *_args, **_kwargs: Response(),
    )

    with pytest.raises(RatelimitException, match="Stack Exchange IP rate limit"):
        StackOverflow(timeout=5).request("GET", StackOverflow.search_url, params={})


def test_specialized_news_engines_parse_news_cards() -> None:
    brave_html = """
    <div data-type="news">
      <a class="result-header" href="https://news.example/brave"><span class="snippet-title">Brave title</span></a>
      <p class="desc">Brave description</p>
    </div>
    """
    brave = BraveNews(timeout=5).post_extract_results(BraveNews(timeout=5).extract_results(brave_html))

    assert brave[0].href == "https://news.example/brave"
    assert brave[0].body == "Brave description"


def test_qwant_parser_keeps_only_web_results() -> None:
    output = Qwant(timeout=5).extract_results(
        '{"status":"success","data":{"result":{"items":{"mainline":['
        '{"type":"ads","items":[{"title":"Ad","url":"https://ads.example"}]},'
        '{"type":"web","items":[{"title":"Result","url":"https://example.com/page","desc":"Body"}]}'
        ']}}}}'
    )

    assert [(row.title, row.href, row.body) for row in output] == [
        ("Result", "https://example.com/page", "Body"),
    ]


def test_qwant_and_yep_enable_safe_search_in_payloads() -> None:
    qwant = Qwant(timeout=5).build_payload("query", "us-en", "on", None)
    yep = Yep(timeout=5).build_payload("query", "us-en", "on", None)

    assert qwant["safesearch"] == "2"
    assert yep["safeSearch"] == "strict"


def test_yep_parser_cleans_html_snippet_and_invalid_links() -> None:
    output = Yep(timeout=5).extract_results(
        '[null,{"results":['
        '{"title":"Result","url":"https://example.com/page","snippet":"Use <b>predicate</b> locks &amp; SSI"},'
        '{"title":"Internal","url":"/search?q=x","snippet":"ignore"}'
        ']}]'
    )

    assert [(row.title, row.href, row.body) for row in output] == [
        ("Result", "https://example.com/page", "Use predicate locks & SSI"),
    ]


@pytest.mark.parametrize(
    ("engine", "body"),
    [
        (Qwant(timeout=5), '{"data":{"error_data":{"captchaUrl":"https://captcha.example"}}}'),
        (Yep(timeout=5), "<html>Cloudflare challenge</html>"),
    ],
)
def test_json_engines_report_antibot_as_rate_limit(monkeypatch, engine, body: str) -> None:
    class Response:
        status_code = 403
        text = body

    monkeypatch.setattr(engine.http_client, "request", lambda *_args, **_kwargs: Response())

    with pytest.raises(RatelimitException, match="captcha"):
        engine.request("GET", engine.search_url)
