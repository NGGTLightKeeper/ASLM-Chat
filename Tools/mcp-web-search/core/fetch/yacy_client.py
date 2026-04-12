# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
YaCy search provider (seed/embryo implementation).

Refactored from legacy deep-research/src/yacy_client.py:
  - Removed import from src.models, uses core.models instead
  - Connection settings loaded from environment / defaults (no hardcoded creds)
  - Added is_available() health-check helper

Marked as MVP / "seed": covers basic global search and URL indexing.
Full features (collection routing, federation, auth mgmt) are in TODO.md.

Public API
----------
YaCyClient              -- synchronous search + indexing client
async_yacy_search(...)  -- asyncio-friendly wrapper
async_add_to_yacy_index(...) -- submit a URL for indexing
is_yacy_available()     -- quick connectivity check
"""

from __future__ import annotations

import html as _html_mod
import logging
import os
from typing import Optional

from core.models.search import SearchResult

logger = logging.getLogger("core.fetch.yacy_client")

# ---------------------------------------------------------------------------
# Default connection settings (override via environment)
# ---------------------------------------------------------------------------

_DEFAULT_URL = os.getenv("YACY_URL", "http://localhost:8090")
_DEFAULT_USER = os.getenv("YACY_USER", "admin")
_DEFAULT_PASS = os.getenv("YACY_PASS", "admin123")


# ---------------------------------------------------------------------------
# YaCyClient
# ---------------------------------------------------------------------------

class YaCyClient:
    """Client for local YaCy search and lightweight indexing requests."""

    def __init__(
        self,
        base_url: str = _DEFAULT_URL,
        user: str = _DEFAULT_USER,
        password: str = _DEFAULT_PASS,
    ) -> None:
        import requests
        from requests.auth import HTTPBasicAuth, HTTPDigestAuth

        self.base_url = base_url.rstrip("/")
        self.user = user
        self.password = password
        self._auth_basic = HTTPBasicAuth(user, password)
        self._auth_digest = HTTPDigestAuth(user, password)
        self._requests = requests

    # -- HTTP helpers --------------------------------------------------------

    def _get(self, path: str, params: dict, timeout: int = 10) -> Optional[dict]:
        """Execute a GET request with basic-auth and digest fallback."""
        url = f"{self.base_url}{path}"
        try:
            resp = self._requests.get(url, params=params, auth=self._auth_basic, timeout=timeout)
            if resp.status_code == 401:
                resp = self._requests.get(url, params=params, auth=self._auth_digest, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except self._requests.RequestException as exc:
            logger.debug("YaCy request failed for %s: %s", path, exc)
            return None
        except ValueError as exc:
            logger.debug("YaCy invalid JSON for %s: %s", path, exc)
            return None

    # -- Health check --------------------------------------------------------

    def is_available(self, timeout: int = 3) -> bool:
        """Return True when YaCy responds within *timeout* seconds."""
        try:
            resp = self._requests.get(
                f"{self.base_url}/yacysearch.json",
                params={"query": "ping", "maximumRecords": 1},
                auth=self._auth_basic,
                timeout=timeout,
            )
            return resp.status_code in (200, 401)
        except Exception:
            return False

    # -- Search helpers ------------------------------------------------------

    def search(
        self,
        query: str,
        max_results: int = 10,
        collection: Optional[str] = None,
        resource: str = "global",
    ) -> list[SearchResult]:
        """Search YaCy and map the API response into SearchResult objects."""
        params: dict = {
            "query": query,
            "resource": resource,
            "maximumRecords": max_results,
            "verify": "false",
            "contentdom": "text",
        }
        if collection:
            params["collection"] = collection

        data = self._get("/yacysearch.json", params)
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
                    title=_html_mod.unescape(item.get("title", "")),
                    snippet=_html_mod.unescape(item.get("description", "")),
                    engine=f"yacy_{resource}",
                )
            )
        return results

    # -- Indexing helpers ----------------------------------------------------

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
            resp = self._requests.get(
                f"{self.base_url}/Crawler_p.html",
                params=params,
                auth=self._auth_basic,
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Async wrappers
# ---------------------------------------------------------------------------

async def async_yacy_search(
    query: str,
    max_results: int = 10,
    collection: Optional[str] = None,
    resource: str = "global",
) -> list[SearchResult]:
    """Run YaCy search in a thread executor."""
    import asyncio

    def _sync() -> list[SearchResult]:
        return YaCyClient().search(
            query=query,
            max_results=max_results,
            collection=collection,
            resource=resource,
        )

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync)


async def async_add_to_yacy_index(url: str) -> bool:
    """Submit a URL to YaCy index in a thread executor."""
    import asyncio

    def _sync() -> bool:
        return YaCyClient().add_url_to_index(url)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync)


def is_yacy_available(timeout: int = 2) -> bool:
    """Synchronous connectivity check for YaCy."""
    try:
        return YaCyClient().is_available(timeout=timeout)
    except Exception:
        return False
