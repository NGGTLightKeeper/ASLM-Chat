"""Bing News search engine."""

from collections.abc import Mapping
from typing import Any, ClassVar

from .bing import Bing


class BingNews(Bing):
    """Specialized Bing news results."""

    name = "bing_news"
    provider = "bing"
    search_url = "https://www.bing.com/news/infinitescrollajax"

    items_xpath = "//div[contains(@class, 'newsitem')]"
    elements_xpath: ClassVar[Mapping[str, str]] = {
        "title": ".//a[contains(@class, 'title')]//text()",
        "href": ".//a[contains(@class, 'title')]/@href",
        "body": ".//div[contains(@class, 'snippet')]//text()",
    }

    def build_payload(
        self,
        query: str,
        region: str,
        safesearch: str,  # noqa: ARG002
        timelimit: str | None,
        page: int = 1,
        **kwargs: str,  # noqa: ARG002
    ) -> dict[str, Any]:
        country, lang = region.lower().split("-")
        market = f"{lang}-{country.upper()}"
        self.http_client.client.headers_update({"Accept-Language": f"{market},{lang};q=0.9"})
        payload: dict[str, Any] = {
            "q": query,
            "InfiniteScroll": "1",
            "first": str((page - 1) * 10 + 1),
            "SFX": str(page - 1),
            "form": "PTFTNR",
            "mkt": market,
        }
        if timelimit:
            payload["qft"] = {
                "d": 'interval="4"',
                "w": 'interval="7"',
                "m": 'interval="9"',
                "y": 'interval="9"',
            }.get(timelimit, 'interval="9"')
        return payload
