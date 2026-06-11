"""Stack Overflow search through the public Stack Exchange API."""

import json
from typing import Any

from ..base import BaseSearchEngine
from ..exceptions import DDGSException, RatelimitException
from ..results import TextResult


class StackOverflow(BaseSearchEngine[TextResult]):
    """Specialist engine for programming questions (disabled — not used in auto routing)."""

    disabled = True
    name = "stackoverflow"
    category = "text"
    provider = "stackexchange"
    priority = 2

    search_url = "https://api.stackexchange.com/2.3/search/advanced"
    search_method = "GET"

    def __init__(
        self,
        proxy: str | None = None,
        timeout: int | None = None,
        *,
        verify: bool | str = True,
    ) -> None:
        super().__init__(proxy=proxy, timeout=timeout, verify=verify)
        self._api_timeout = float(timeout or 10)

    def request(self, method: str, url: str, **kwargs: Any) -> str:  # noqa: ARG002
        """Use the JSON API transport instead of the generic HTML engine client."""
        from curl_cffi import requests as cffi_requests

        try:
            response = cffi_requests.get(
                url,
                params=kwargs.get("params") or {},
                impersonate="chrome124",
                timeout=self._api_timeout,
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            )
            lowered = response.text.lower()
            if response.status_code == 429 or (
                "too many requests" in lowered
                or "temporarily rate limited" in lowered
                or "unusually high number of requests" in lowered
            ):
                raise RatelimitException("Stack Exchange IP rate limit")
            response.raise_for_status()
            return response.text
        except RatelimitException:
            raise
        except Exception as exc:
            raise DDGSException(f"Stack Exchange API request failed: {exc}") from exc

    def build_payload(
        self,
        query: str,
        region: str,  # noqa: ARG002
        safesearch: str,  # noqa: ARG002
        timelimit: str | None,  # noqa: ARG002
        page: int = 1,
        **kwargs: str,  # noqa: ARG002
    ) -> dict[str, Any]:
        return {
            "site": "stackoverflow",
            "q": query,
            "page": str(max(1, page)),
            "pagesize": "10",
            "order": "desc",
            "sort": "relevance",
            "filter": "withbody",
        }

    def extract_results(self, html_text: str) -> list[TextResult]:
        payload = json.loads(html_text)
        results: list[TextResult] = []
        for item in payload.get("items") or []:
            title = str(item.get("title") or "")
            href = str(item.get("link") or "")
            tags = ", ".join(str(tag) for tag in item.get("tags") or [])
            score = int(item.get("score") or 0)
            answers = int(item.get("answer_count") or 0)
            accepted = "accepted answer" if item.get("is_answered") else "no accepted answer"
            body = f"Stack Overflow question tagged {tags}. Score {score}; {answers} answers; {accepted}."
            if title and href:
                results.append(TextResult(title=title, href=href, body=body))
        return results
