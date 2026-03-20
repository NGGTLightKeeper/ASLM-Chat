# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import html
from typing import Optional

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from src.models import SearchResult

YACY_URL = "http://localhost:8090"
YACY_USER = "admin"
YACY_PASS = "admin123"


# YaCy client implementation.
class YaCyClient:
    """Client for local YaCy search and lightweight indexing requests."""

    # Construction helpers.
    def __init__(
        self,
        base_url: str = YACY_URL,
        user: str = YACY_USER,
        password: str = YACY_PASS,
    ) -> None:
        """Store connection settings for the local YaCy instance."""

        self.base_url = base_url.rstrip("/")
        self.user = user
        self.password = password
        self.auth = HTTPBasicAuth(self.user, self.password)

    # HTTP helpers.
    def _do_request(self, params: dict) -> Optional[dict]:
        """Execute a search request with basic-auth and digest fallback."""

        url = f"{self.base_url}/yacysearch.json"
        try:
            response = requests.get(url, params=params, auth=self.auth, timeout=10)
            if response.status_code == 401:
                response = requests.get(
                    url,
                    params=params,
                    auth=HTTPDigestAuth(self.user, self.password),
                    timeout=10,
                )
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            return None
        except ValueError:
            return None

    # Search helpers.
    def search(
        self,
        query: str,
        max_results: int = 10,
        collection: Optional[str] = None,
        resource: str = "global",
    ) -> list[SearchResult]:
        """Search YaCy and map the API response into SearchResult objects."""

        params = {
            "query": query,
            "resource": resource,
            "maximumRecords": max_results,
            "verify": "false",
            "contentdom": "text",
        }
        if collection:
            params["collection"] = collection

        data = self._do_request(params)
        if not data:
            return []

        channels = data.get("channels", [])
        if not channels:
            return []

        results: list[SearchResult] = []
        for item in channels[0].get("items", []):
            link = item.get("link", "")
            if not link:
                continue

            results.append(
                SearchResult(
                    url=link,
                    title=html.unescape(item.get("title", "")),
                    snippet=html.unescape(item.get("description", "")),
                    engine=f"yacy_{resource}",
                )
            )

        return results

    # Indexing helpers.
    def add_url_to_index(self, url: str) -> bool:
        """Submit a single URL to YaCy for lightweight indexing."""

        params = {
            "crawlingstart": "",
            "crawlingURL": url,
            "crawlingDepth": "1",
            "crawlingDomMaxPages": "5",
            "indexText": "on",
            "indexMedia": "off",
            "storeHTCache": "on",
            "cachePolicy": "iffresh",
        }
        try:
            response = requests.get(
                f"{self.base_url}/Crawler_p.html",
                params=params,
                auth=self.auth,
                timeout=5,
            )
            return response.status_code == 200
        except Exception:
            return False


# Async wrappers.
async def async_yacy_search(
    query: str,
    max_results: int = 10,
    collection: Optional[str] = None,
    resource: str = "global",
) -> list[SearchResult]:
    """Run YaCy search in a thread executor."""

    import asyncio

    # Keep the public API async without changing the synchronous client implementation.
    def _sync() -> list[SearchResult]:
        client = YaCyClient()
        return client.search(
            query=query,
            max_results=max_results,
            collection=collection,
            resource=resource,
        )

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync)

# Async wrappers.
async def async_add_to_yacy_index(url: str) -> bool:
    """Run the index submission call in a thread executor."""

    import asyncio

    # Keep the public API async while reusing the sync client.
    def _sync() -> bool:
        client = YaCyClient()
        return client.add_url_to_index(url)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync)


# Local smoke-test entry point.
if __name__ == "__main__":
    client = YaCyClient()
    results = client.search("linux", max_results=3)
    print(f"Found: {len(results)}")
    for result in results:
        print(f"- {result.title} ({result.url})")
