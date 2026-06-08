"""Direct Bing search engine."""

import base64
from collections.abc import Mapping
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlparse

from ..base import BaseSearchEngine
from ..exceptions import DDGSException, RatelimitException
from ..results import TextResult


class Bing(BaseSearchEngine[TextResult]):
    """Bing HTML search engine."""

    name = "bing"
    category = "text"
    provider = "bing"

    search_url = "https://www.bing.com/search"
    search_method = "GET"
    headers_update: ClassVar[dict[str, str]] = {
        "Referer": "https://www.bing.com/",
    }

    items_xpath = "//li[contains(@class, 'b_algo')]"
    elements_xpath: ClassVar[Mapping[str, str]] = {
        "title": ".//h2//text()",
        "href": ".//h2/a/@href",
        "body": ".//div[contains(@class, 'b_caption')]//p//text()",
    }

    def __init__(
        self,
        proxy: str | None = None,
        timeout: int | None = None,
        *,
        verify: bool | str = True,
    ) -> None:
        super().__init__(proxy=proxy, timeout=timeout, verify=verify)
        self._curl_proxy = proxy
        self._curl_timeout = float(timeout or 10)
        self._curl_verify = verify

    def request(self, method: str, url: str, **kwargs: Any) -> str:
        """Fetch Bing through curl_cffi browser impersonation."""
        from curl_cffi import requests as cffi_req

        response = cffi_req.request(
            method,
            url,
            headers=dict(self.headers_update),
            timeout=self._curl_timeout,
            impersonate="chrome124",
            allow_redirects=True,
            proxy=self._curl_proxy,
            verify=self._curl_verify,
            **kwargs,
        )
        if response.status_code == 200:
            return response.text
        if response.status_code == 429:
            raise RatelimitException("HTTP 429")
        if response.status_code in (402, 403):
            raise DDGSException(f"HTTP {response.status_code} forbidden")
        if response.status_code >= 400:
            raise DDGSException(f"HTTP {response.status_code}")
        return ""

    def build_payload(
        self,
        query: str,
        region: str,
        safesearch: str,
        timelimit: str | None,
        page: int = 1,
        **kwargs: str,  # noqa: ARG002
    ) -> dict[str, Any]:
        country, lang = region.lower().split("-")
        market = f"{lang}-{country.upper()}"
        self.http_client.client.headers_update({"Accept-Language": f"{market},{lang};q=0.9"})
        payload = {
            "q": query,
            "mkt": market,
            "adlt": {"on": "strict", "moderate": "moderate", "off": "off"}[safesearch.lower()],
        }
        if page > 1:
            payload["first"] = str((page - 1) * 10 + 1)
        if timelimit:
            payload["filters"] = f'ex1:"ez{timelimit}"'
        return payload

    def extract_results(self, html_text: str) -> list[TextResult]:
        """Parse organic results while excluding Bing's decorative snippet icons."""
        tree = self.extract_tree(html_text)
        output: list[TextResult] = []
        for item in tree.xpath(self.items_xpath):
            for icon in item.xpath(".//span[contains(@class, 'algoSlug_icon')]"):
                parent = icon.getparent()
                if parent is None:
                    continue
                if icon.tail:
                    previous = icon.getprevious()
                    if previous is not None:
                        previous.tail = (previous.tail or "") + icon.tail
                    else:
                        parent.text = (parent.text or "") + icon.tail
                parent.remove(icon)
            result = TextResult()
            for key, xpath in self.elements_xpath.items():
                setattr(result, key, " ".join("".join(item.xpath(xpath)).split()))
            output.append(result)
        return output

    def post_extract_results(self, results: list[TextResult]) -> list[TextResult]:
        output = []
        for result in results:
            if "bing.com/ck/a" in result.href:
                encoded = parse_qs(urlparse(result.href).query).get("u", [""])[0]
                if encoded.startswith("a1"):
                    try:
                        payload = encoded[2:]
                        payload += "=" * (-len(payload) % 4)
                        result.href = base64.urlsafe_b64decode(payload).decode("utf-8")
                    except (ValueError, UnicodeDecodeError):
                        pass
            if result.title and result.href.startswith("http") and "bing.com/ck/a" not in result.href:
                output.append(result)
        return output
