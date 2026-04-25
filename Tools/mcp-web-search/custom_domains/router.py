from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable
from urllib.parse import urlparse

from custom_domains.amazon import fetch_amazon_snapshot
from custom_domains.reddit import fetch_reddit_json, is_reddit
from custom_domains.x import fetch_x_post, is_x_post

logger = logging.getLogger("custom_domains.router")

_AMAZON_HOSTS = frozenset({
    "amazon.com", "amazon.co.uk", "amazon.de",
    "amazon.fr", "amazon.it", "amazon.es", "amazon.co.jp",
})
_EBAY_HOSTS = frozenset({
    "ebay.com", "ebay.co.uk", "ebay.de", "ebay.fr", "ebay.it",
})


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")


@dataclass
class CustomRoute:
    name: str
    is_heavy: bool
    quality_score: float
    matches: Callable[[str], bool]
    # async (url, timeout) → markdown text | None
    _fetch: Callable[[str, float], Awaitable[str | None]]

    async def fetch_preview(self, url: str, timeout: float) -> str | None:
        try:
            return await asyncio.wait_for(self._fetch(url, timeout), timeout=timeout)
        except asyncio.TimeoutError:
            logger.debug("custom route %s timed out for %s", self.name, url)
            return None
        except Exception:
            logger.debug("custom route %s failed for %s", self.name, url, exc_info=True)
            return None


# ---------------------------------------------------------------------------
# Fetch wrappers — normalise all returns to str | None
# ---------------------------------------------------------------------------

async def _amazon_fetch(url: str, timeout: float) -> str | None:
    snapshot = await fetch_amazon_snapshot(url, timeout=timeout)
    markdown = str(snapshot.get("markdown") or "").strip()
    if not markdown:
        return None
    if snapshot.get("blocked_like"):
        return None
    if "continue shopping" in markdown.lower():
        return None
    return markdown


async def _reddit_fetch(url: str, timeout: float) -> str | None:
    text = await fetch_reddit_json(url)
    if text and not text.startswith("Error:"):
        return text
    return None


async def _x_fetch(url: str, timeout: float) -> str | None:
    text = await fetch_x_post(url, timeout)
    if text and not text.startswith("Error:"):
        return text
    return None


async def _heavy_noop(url: str, timeout: float) -> str | None:
    return None


# ---------------------------------------------------------------------------
# Route registry
# ---------------------------------------------------------------------------

_ROUTES: list[CustomRoute] = [
    CustomRoute(
        name="amazon",
        is_heavy=False,
        quality_score=0.80,
        matches=lambda url: _host(url) in _AMAZON_HOSTS,
        _fetch=_amazon_fetch,
    ),
    CustomRoute(
        name="reddit",
        is_heavy=False,
        quality_score=0.75,
        matches=is_reddit,
        _fetch=_reddit_fetch,
    ),
    CustomRoute(
        name="x",
        is_heavy=False,
        quality_score=0.70,
        matches=is_x_post,
        _fetch=_x_fetch,
    ),
    CustomRoute(
        name="ebay",
        is_heavy=True,
        quality_score=0.80,
        matches=lambda url: _host(url) in _EBAY_HOSTS,
        _fetch=_heavy_noop,
    ),
    CustomRoute(
        name="dns_shop",
        is_heavy=True,
        quality_score=0.80,
        matches=lambda url: _host(url) == "dns-shop.ru",
        _fetch=lambda url, timeout: asyncio.sleep(0, result=None),
    ),
    CustomRoute(
        name="citilink",
        is_heavy=True,
        quality_score=0.80,
        matches=lambda url: _host(url) == "citilink.ru",
        _fetch=lambda url, timeout: asyncio.sleep(0, result=None),
    ),
]


def get_custom_route(url: str) -> CustomRoute | None:
    for route in _ROUTES:
        if route.matches(url):
            return route
    return None
