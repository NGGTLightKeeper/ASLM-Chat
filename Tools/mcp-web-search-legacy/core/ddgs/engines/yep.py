"""Yep web search through its JSON API."""

import json
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

from ..base import BaseSearchEngine
from ..exceptions import DDGSException, RatelimitException
from ..results import TextResult

_HTML_TAG_RE = re.compile(r"<[^>]+>")


class Yep(BaseSearchEngine[TextResult]):
    """General web results from Yep's independent index."""

    name = "yep"
    category = "text"
    provider = "yep"

    search_url = "https://api.yep.com/search"
    search_method = "GET"
    headers_update = {
        "Accept": "application/json",
        "Origin": "https://yep.com",
        "Referer": "https://yep.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }

    def request(self, method: str, url: str, **kwargs: Any) -> str:
        response = self.http_client.request(method, url, **kwargs)
        body = response.text or ""
        lowered = body.lower()
        if response.status_code == 200:
            return body
        if response.status_code == 429 or (
            response.status_code == 403
            and ("cloudflare" in lowered or "challenge" in lowered or "captcha" in lowered)
        ):
            raise RatelimitException("Yep anti-bot captcha or rate limit")
        raise DDGSException(f"Yep HTTP {response.status_code}")

    def build_payload(
        self,
        query: str,
        region: str,
        safesearch: str,
        timelimit: str | None,  # noqa: ARG002
        page: int = 1,  # noqa: ARG002
        **kwargs: str,  # noqa: ARG002
    ) -> dict[str, Any]:
        _country, language = region.replace("_", "-").lower().split("-", 1)
        safe = {"off": "off", "moderate": "moderate", "on": "strict"}.get(
            safesearch.lower(), "moderate",
        )
        return {
            "query": query,
            "safeSearch": safe,
            "limit": "20",
            "hl": language,
        }

    def extract_results(self, html_text: str) -> list[TextResult]:
        payload = json.loads(html_text)
        items = payload[1].get("results", []) if isinstance(payload, list) and len(payload) > 1 else []
        results: list[TextResult] = []
        for item in items:
            title = str(item.get("title") or "")
            href = str(item.get("url") or "")
            body = " ".join(unescape(_HTML_TAG_RE.sub(" ", str(item.get("snippet") or ""))).split())
            parsed = urlparse(href)
            if title and parsed.scheme in {"http", "https"} and parsed.netloc:
                results.append(TextResult(title=title, href=href, body=body))
        return results
