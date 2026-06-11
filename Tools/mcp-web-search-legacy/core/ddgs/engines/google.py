"""Google search engine implementation."""

from collections.abc import Mapping
from typing import Any, ClassVar
from urllib.parse import parse_qs, unquote, urlparse

from lxml import html as lhtml

from ..base import BaseSearchEngine
from ..exceptions import DDGSException
from ..http_client import HttpClient
from ..results import TextResult

_DESKTOP_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _unwrap_google_href(href: str) -> str:
    """Decode Google redirect URLs to the destination link."""
    if not href:
        return ""
    if href.startswith("/url?"):
        href = f"https://www.google.com{href}"
    parsed = urlparse(href)
    if parsed.netloc.endswith("google.com") and parsed.path == "/url":
        target = parse_qs(parsed.query).get("q", [""])[0]
        return unquote(target) if target else href
    return href


def _is_consent_page(html_text: str) -> bool:
    lower = (html_text or "").lower()
    return "before you continue to google" in lower and "consent.google.com/save" in lower


def _consent_form_payload(html_text: str, *, accept_all: bool) -> tuple[str, dict[str, str]] | None:
    tree = lhtml.fromstring(html_text)
    for form in tree.xpath("//form[contains(@action,'consent.google.com/save')]"):
        fields = {
            name: value
            for name, value in (
                (item.get("name"), item.get("value") or "")
                for item in form.xpath(".//input[@name]")
            )
            if name
        }
        if accept_all and fields.get("set_sc") == "true":
            return str(form.get("action") or ""), fields
        if not accept_all and fields.get("set_eom") == "true" and "set_sc" not in fields:
            return str(form.get("action") or ""), fields
    return None


class Google(BaseSearchEngine[TextResult]):
    """Google search engine (desktop Chrome fingerprint + simplified HTML)."""

    name = "google"
    category = "text"
    provider = "google"

    search_url = "https://www.google.com/search"
    search_method = "GET"
    headers_update: ClassVar[dict[str, str]] = {
        "User-Agent": _DESKTOP_CHROME_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Desktop/basic SERP: result anchor wraps the h3 title.
    items_xpath = "//a[@href and .//h3 and not(contains(@href,'google.com/search'))]"
    elements_xpath: ClassVar[Mapping[str, str]] = {
        "title": ".//h3//text()",
        "href": "./@href",
        "body": "./div[contains(@class,'VwiC3b') or contains(@class,'yXK7lf')]//text()",
    }

    def __init__(self, proxy: str | None = None, timeout: int | None = None, *, verify: bool | str = True) -> None:
        self.http_client = HttpClient(
            proxy=proxy,
            timeout=timeout,
            verify=verify,
            impersonate="chrome",
            impersonate_os="windows",
        )
        self.http_client.client.headers_update(self.headers_update)
        self.results: list[TextResult] = []

    def build_payload(
        self,
        query: str,
        region: str,
        safesearch: str,
        timelimit: str | None,
        page: int = 1,
        **kwargs: str,  # noqa: ARG002
    ) -> dict[str, Any]:
        """Build a payload for the Google search request."""
        self.http_client.client.set_cookies("https://www.google.com", {"CONSENT": "YES+"})
        safesearch_base = {"on": "high", "moderate": "medium", "off": "off"}
        start = (page - 1) * 10
        payload = {
            "q": query,
            "filter": "0",
            "safe": safesearch_base[safesearch.lower()],
            "start": str(start),
            "ie": "utf8",
            "oe": "utf8",
            "gbv": "1",
        }
        country, lang = region.split("-")
        payload["hl"] = f"{lang}-{country.upper()}"
        payload["lr"] = f"lang_{lang}"
        payload["cr"] = f"country{country.upper()}"
        payload["gl"] = country.upper()
        if timelimit:
            payload["tbs"] = f"qdr:{timelimit}"
        return payload

    def pre_process_html(self, html_text: str) -> str:
        """Surface Google's short bot-protection pages as routing failures."""
        lower = html_text.lower()
        if _is_consent_page(html_text):
            raise DDGSException("google consent")
        if "enablejs" in lower or "/httpservice/retry/enablejs" in lower:
            raise DDGSException("google js required")
        if len(html_text) < 5000 and ("/sorry/" in lower or "unusual traffic" in lower):
            raise DDGSException("google captcha")
        return html_text

    def _fetch_html(self, *, params: dict[str, Any]) -> str | None:
        return self.request(self.search_method, self.search_url, params=params)

    def _accept_consent(self, html_text: str) -> str | None:
        parsed = _consent_form_payload(html_text, accept_all=True)
        if parsed is None:
            parsed = _consent_form_payload(html_text, accept_all=False)
        if parsed is None:
            raise DDGSException("google consent form missing")
        action, fields = parsed
        if not action.startswith("http"):
            action = f"https://consent.google.com{action}"
        response = self.http_client.request("POST", action, data=fields)
        if response.status_code not in {200, 302, 303}:
            raise DDGSException(f"google consent HTTP {response.status_code}")
        if response.text and not _is_consent_page(response.text):
            return response.text
        continue_url = fields.get("continue")
        if continue_url:
            follow = self.http_client.request("GET", continue_url)
            if follow.status_code == 200 and follow.text:
                return follow.text
        return response.text or None

    def search(
        self,
        query: str,
        region: str = "us-en",
        safesearch: str = "moderate",
        timelimit: str | None = None,
        page: int = 1,
        **kwargs: str,
    ) -> list[TextResult] | None:
        payload = self.build_payload(
            query=query,
            region=region,
            safesearch=safesearch,
            timelimit=timelimit,
            page=page,
            **kwargs,
        )
        html_text = self._fetch_html(params=payload)
        if not html_text:
            return None
        if _is_consent_page(html_text):
            html_text = self._accept_consent(html_text)
        if not html_text:
            return None
        results = self.extract_results(html_text)
        return self.post_extract_results(results)

    def post_extract_results(self, results: list[TextResult]) -> list[TextResult]:
        """Post-process search results."""
        post_results = []
        for result in results:
            result.href = _unwrap_google_href(result.href)
            if not result.title or not result.href.startswith("http"):
                continue
            host = urlparse(result.href).netloc.lower()
            if host.endswith("google.com"):
                continue
            post_results.append(result)
        return post_results
