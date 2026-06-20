"""Qwant web search through its JSON API."""

import json
from typing import Any
from urllib.parse import urlparse

from ..base import BaseSearchEngine
from ..exceptions import DDGSException, RatelimitException
from ..results import TextResult


class Qwant(BaseSearchEngine[TextResult]):
    """General web results from Qwant, excluding ads and side modules."""

    name = "qwant"
    category = "text"
    provider = "qwant"

    search_url = "https://api.qwant.com/v3/search/web"
    search_method = "GET"
    headers_update = {
        "Accept": "application/json",
        "Origin": "https://www.qwant.com",
        "Referer": "https://www.qwant.com/",
    }

    def request(self, method: str, url: str, **kwargs: Any) -> str:
        response = self.http_client.request(method, url, **kwargs)
        body = response.text or ""
        if response.status_code == 200:
            return body
        if response.status_code == 429 or "captchaUrl" in body or "captcha-delivery.com" in body:
            raise RatelimitException("Qwant captcha or rate limit")
        raise DDGSException(f"Qwant HTTP {response.status_code}")

    def build_payload(
        self,
        query: str,
        region: str,
        safesearch: str,
        timelimit: str | None,  # noqa: ARG002
        page: int = 1,
        **kwargs: str,  # noqa: ARG002
    ) -> dict[str, Any]:
        country, language = region.replace("_", "-").lower().split("-", 1)
        safe = {"off": "0", "moderate": "1", "on": "2"}.get(safesearch.lower(), "1")
        return {
            "q": query,
            "count": "10",
            "locale": f"{language}_{country.upper()}",
            "offset": str(max(0, page - 1) * 10),
            "device": "desktop",
            "safesearch": safe,
            "tgp": "1",
            "display": "true",
            "llm": "false",
        }

    def extract_results(self, html_text: str) -> list[TextResult]:
        payload = json.loads(html_text)
        if payload.get("status") != "success":
            data = payload.get("data") or {}
            if data.get("error_code") == 24:
                raise RatelimitException("Qwant rate limit")
            if (data.get("error_data") or {}).get("captchaUrl"):
                raise RatelimitException("Qwant captcha")
            raise DDGSException(f"Qwant API error: {data.get('message') or 'unknown'}")

        mainline = (
            payload.get("data", {})
            .get("result", {})
            .get("items", {})
            .get("mainline", [])
        )
        results: list[TextResult] = []
        for block in mainline:
            if block.get("type") != "web":
                continue
            for item in block.get("items") or []:
                title = str(item.get("title") or "")
                href = str(item.get("url") or "")
                body = str(item.get("desc") or "")
                parsed = urlparse(href)
                if title and parsed.scheme in {"http", "https"} and parsed.netloc:
                    results.append(TextResult(title=title, href=href, body=body))
        return results
