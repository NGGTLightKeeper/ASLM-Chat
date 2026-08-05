# Copyright NEXTGGTECH. Elastic License 2.0.

"""Hosted search-API clients (optional supplement layer).

Ported from the legacy `core/fetch/hosted_clients.py` and rebuilt async-first on httpx
(the new stack's HTTP client) instead of sync `requests` in a thread pool. Every client
exposes the same Tavily-style shape — `search() -> list[HostedResult]` — where
content-bearing providers (Tavily advanced, Firecrawl) carry the full page text in
`HostedResult.content`. That text is pre-populated into SourceCache by `hosted_stream`
so the shared read_page extraction/compaction pipeline runs on it without a re-fetch.

`provider_family` drives consensus voting: SerpApi serves Google's index, so it votes
with the Google scrape parser; Tavily/Firecrawl/Brave are their own families.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from core.config.api_keys import HostedSearchApiKeysSection, load_api_keys

logger = logging.getLogger("services.web_search")

# Tavily/Firecrawl "advanced" crawl returns full page text (more credits); the cheap
# tiers only return short snippets, which defeats the whole point of the content feed.
_TAVILY_SEARCH_DEPTH = "advanced"

_API_QUERY_STRIP_RE = re.compile(r"[\[\]*\\]")


# One hosted result row. `content` is non-empty only for content-bearing providers.
@dataclass(slots=True)
class HostedResult:
    url: str
    title: str
    snippet: str
    provider: str
    provider_family: str
    published_date: str = ""
    content: str = ""


# Strip characters that break hosted API query parsers ([ ] * \ unbalanced quotes).
def sanitize_query_for_api(query: str) -> str:
    query = _API_QUERY_STRIP_RE.sub("", query or "")
    if query.count('"') % 2 != 0:
        query = query.replace('"', "")
    return " ".join(query.split())


class HostedProvider(Protocol):
    name: str
    provider_family: str
    returns_content: bool

    def key(self, keys: HostedSearchApiKeysSection) -> str | None: ...

    async def search(
        self, client: httpx.AsyncClient, query: str, *, max_results: int
    ) -> list[HostedResult]: ...


# --- Tavily: POST /search, advanced depth → raw_content (full page text) ----------
class TavilyClient:
    name = "tavily"
    provider_family = "tavily"
    returns_content = True
    BASE_URL = "https://api.tavily.com/search"

    def key(self, keys: HostedSearchApiKeysSection) -> str | None:
        return keys.tavily_api_key

    async def search(self, client, query, *, max_results):
        api_key = load_api_keys().search.hosted_api.tavily_api_key
        if not api_key:
            return []
        # serp mode: cheap consensus rows only — basic depth, no raw page text, and
        # nothing fed into SourceCache (a snippet cached as "the page" would poison
        # read_page with a 200-char stub).
        content_mode = provider_mode(self.name) == "content"
        payload: dict[str, Any] = {
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": _TAVILY_SEARCH_DEPTH if content_mode else "basic",
            "include_answer": False,
            "include_raw_content": content_mode,
        }
        data = await _post_json(client, self.BASE_URL, json=payload, provider=self.name)
        out: list[HostedResult] = []
        for item in (data or {}).get("results", []):
            url = item.get("url") or ""
            if not url:
                continue
            content = (item.get("raw_content") or item.get("content") or "") if content_mode else ""
            out.append(HostedResult(
                url=url,
                title=item.get("title") or "",
                snippet=(item.get("content") or "")[:2000],
                provider=self.name,
                provider_family=self.provider_family,
                published_date=str(item.get("published_date") or ""),
                content=content,
            ))
        return out


# --- Firecrawl: POST /v1/search with scrapeOptions → markdown (full page text) ----
class FirecrawlClient:
    name = "firecrawl"
    provider_family = "firecrawl"
    returns_content = True
    BASE_URL = "https://api.firecrawl.dev/v1/search"

    def key(self, keys: HostedSearchApiKeysSection) -> str | None:
        return keys.firecrawl_api_key

    async def search(self, client, query, *, max_results):
        api_key = load_api_keys().search.hosted_api.firecrawl_api_key
        if not api_key:
            return []
        # serp mode (the default): plain search rows, no per-result headless scrape.
        # Content mode was measured at ~9.4s — past the medium hosted deadline, so the
        # scrape credits were being spent on results the deadline then threw away.
        content_mode = provider_mode(self.name) == "content"
        payload: dict[str, Any] = {
            "query": query,
            "limit": max_results,
        }
        if content_mode:
            payload["scrapeOptions"] = {"formats": ["markdown"]}
        data = await _post_json(
            client, self.BASE_URL, json=payload, provider=self.name,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        out: list[HostedResult] = []
        for item in (data or {}).get("data", []):
            url = item.get("url") or ""
            if not url:
                continue
            meta = item.get("metadata") or {}
            out.append(HostedResult(
                url=url,
                title=item.get("title") or meta.get("title") or "",
                snippet=(item.get("description") or meta.get("description") or "")[:2000],
                provider=self.name,
                provider_family=self.provider_family,
                published_date=str(meta.get("publishedTime") or ""),
                content=(item.get("markdown") or "") if content_mode else "",
            ))
        return out


# --- Brave Search API: GET /res/v1/web/search (SERP rows + rich snippets) ----------
class BraveClient:
    name = "brave"
    provider_family = "brave"
    returns_content = False
    BASE_URL = "https://api.search.brave.com/res/v1/web/search"

    def key(self, keys: HostedSearchApiKeysSection) -> str | None:
        return keys.brave_api_key

    async def search(self, client, query, *, max_results):
        api_key = load_api_keys().search.hosted_api.brave_api_key
        if not api_key:
            return []
        params: dict[str, Any] = {"q": query, "count": min(max_results, 20)}
        data = await _get_json(
            client, self.BASE_URL, params=params, provider=self.name,
            headers={"Accept": "application/json", "Accept-Encoding": "gzip",
                     "X-Subscription-Token": api_key},
        )
        out: list[HostedResult] = []
        for item in (data or {}).get("web", {}).get("results", []):
            url = item.get("url") or ""
            if not url:
                continue
            out.append(HostedResult(
                url=url,
                title=item.get("title") or "",
                snippet=(item.get("description") or "")[:2000],
                provider=self.name,
                provider_family=self.provider_family,
                published_date=str(item.get("page_age") or item.get("age") or ""),
            ))
        return out


# --- SerpApi (Google engine): GET /search.json. Votes with the Google scrape family.
class SerpApiClient:
    name = "serpapi"
    provider_family = "google"
    returns_content = False
    BASE_URL = "https://serpapi.com/search.json"

    def key(self, keys: HostedSearchApiKeysSection) -> str | None:
        return keys.serpapi_api_key

    async def search(self, client, query, *, max_results):
        api_key = load_api_keys().search.hosted_api.serpapi_api_key
        if not api_key:
            return []
        params: dict[str, Any] = {
            "q": query, "num": min(max_results, 100), "engine": "google",
            "api_key": api_key, "output": "json",
        }
        data = await _get_json(client, self.BASE_URL, params=params, provider=self.name)
        out: list[HostedResult] = []
        for item in (data or {}).get("organic_results", []):
            url = item.get("link") or ""
            if not url:
                continue
            out.append(HostedResult(
                url=url,
                title=item.get("title") or "",
                snippet=(item.get("snippet") or "")[:2000],
                provider=self.name,
                provider_family=self.provider_family,
                published_date=str(item.get("date") or ""),
            ))
        return out


# Registry of wired providers. Order is the priority used when assigning SERP ranks.
_PROVIDERS: tuple[HostedProvider, ...] = (
    TavilyClient(),
    FirecrawlClient(),
    BraveClient(),
    SerpApiClient(),
)


# Configured mode for a provider: "content" | "serp" | "off" (see HostedApiSection).
def provider_mode(name: str) -> str:
    from core.config import load_search_config

    return str(getattr(load_search_config().hosted_api, name, "serp"))


# Providers that have an API key configured right now and are not switched off.
def available_providers() -> list[HostedProvider]:
    keys = load_api_keys().search.hosted_api
    return [
        p for p in _PROVIDERS
        if (p.key(keys) or "").strip() and provider_mode(p.name) != "off"
    ]


# POST JSON helper; never raises (returns None on any failure).
async def _post_json(client, url, *, json, provider, headers=None):
    try:
        resp = await client.post(url, json=json, headers=headers or {})
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001 — a hosted miss must never sink the search
        logger.warning("[%s] request failed: %s", provider, exc)
        return None


# GET JSON helper; never raises (returns None on any failure).
async def _get_json(client, url, *, params, provider, headers=None):
    try:
        resp = await client.get(url, params=params, headers=headers or {})
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001 — a hosted miss must never sink the search
        logger.warning("[%s] request failed: %s", provider, exc)
        return None
