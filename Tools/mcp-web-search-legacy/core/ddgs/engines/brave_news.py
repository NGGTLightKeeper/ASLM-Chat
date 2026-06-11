"""Brave News search engine."""

from collections.abc import Mapping
from typing import ClassVar

from .brave import Brave


class BraveNews(Brave):
    """Specialized Brave news results."""

    name = "brave_news"
    provider = "brave"
    search_url = "https://search.brave.com/news"

    items_xpath = "//div[@data-type='news']"
    elements_xpath: ClassVar[Mapping[str, str]] = {
        "title": (
            ".//a[div[contains(@class, 'title')]]/div[contains(@class, 'title')]//text()"
            " | .//span[contains(@class, 'snippet-title')]//text()"
        ),
        "href": ".//a[div[contains(@class, 'title')]]/@href | .//a[contains(@class, 'result-header')]/@href",
        "body": (
            ".//div[contains(@class, 'description')]//text()"
            " | .//p[contains(@class, 'desc')]//text()"
        ),
    }
