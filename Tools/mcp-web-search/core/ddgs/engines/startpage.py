"""Startpage search engine implementation."""

import logging
import threading
import time
from collections.abc import Mapping
from typing import Any, ClassVar

from ..base import BaseSearchEngine
from ..exceptions import DDGSException
from ..results import TextResult

logger = logging.getLogger(__name__)


class Startpage(BaseSearchEngine[TextResult]):
    """Startpage search engine."""

    name = "startpage"
    category = "text"
    provider = "google"

    search_url = "https://www.startpage.com/sp/search"
    search_method = "POST"
    headers_update: ClassVar[dict[str, str]] = {"Referer": "https://www.startpage.com/"}

    items_xpath = "//div[contains(@class, 'result')][./a]"
    elements_xpath: ClassVar[Mapping[str, str]] = {
        "title": ".//h2//text()",
        "href": "./a/@href",
        "body": ".//p//text()",
    }
    _sc_code: ClassVar[str] = ""
    _sc_expires_at: ClassVar[float] = 0.0
    _sc_lock: ClassVar[threading.Lock] = threading.Lock()

    def get_sc(self) -> str:
        """Reuse Startpage's short-lived form token instead of burning one request per search."""
        now = time.time()
        if self._sc_code and now < self._sc_expires_at:
            return self._sc_code
        with self._sc_lock:
            now = time.time()
            if self._sc_code and now < self._sc_expires_at:
                return self._sc_code
            resp_text = self.http_client.request("GET", "https://www.startpage.com/").text
            if "/sp/captcha" in resp_text.lower():
                raise DDGSException("startpage captcha")
            tree = self.extract_tree(resp_text)
            sc_elements = tree.xpath('//form[@id="search"]//input[@name="sc"]/@value')
            if not sc_elements:
                raise DDGSException("startpage form token missing")
            type(self)._sc_code = str(sc_elements[0])
            type(self)._sc_expires_at = now + 3600.0
            return self._sc_code

    def pre_process_html(self, html_text: str) -> str:
        if "/sp/captcha" in html_text.lower():
            type(self)._sc_code = ""
            type(self)._sc_expires_at = 0.0
            raise DDGSException("startpage captcha")
        return html_text

    def post_extract_results(self, results: list[TextResult]) -> list[TextResult]:
        """Discard Startpage tracking/navigation links that are not result URLs."""
        return [
            result
            for result in results
            if result.title and result.href.startswith(("http://", "https://"))
        ]

    def build_payload(
        self,
        query: str,
        region: str,
        safesearch: str,
        timelimit: str | None,
        page: int = 1,
        **kwargs: str,  # noqa: ARG002
    ) -> dict[str, Any]:
        """Build a payload for the Startpage search request."""
        country, lang = region.lower().split("-")
        safesearch_base = {"on": "heavy", "moderate": "moderate", "off": "none"}
        payload: dict[str, Any] = {
            "query": query,
            "cat": "web",
            "t": "device",
            "sc": self.get_sc(),
            "lui": "english",
            "language": "english",
            "abp": "1",
            "abd": "0",
            "abe": "0",
            "qsr": f"{lang}_{country.upper()}",
            "qadf": safesearch_base[safesearch.lower()],
            "segment": "organic",
        }
        if page > 1:
            payload["page"] = str(page)
        if timelimit:
            payload["with_date"] = timelimit

        return payload
