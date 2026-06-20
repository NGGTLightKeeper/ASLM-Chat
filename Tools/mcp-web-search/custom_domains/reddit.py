# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import html as html_lib
import json
import logging
import re
from typing import Any
from urllib.parse import urlparse, urlunparse

from core.fetch.thread_pool import io_pool as _io_pool

logger = logging.getLogger("custom_domains.reddit")

_REDDIT_PATTERN = re.compile(r"reddit\.com/r/[^/]+/comments/")
_PRE_JSON_RE = re.compile(r"<pre[^>]*>(.*?)</pre>", re.IGNORECASE | re.DOTALL)


# True when URL looks like a Reddit thread comments page.
def is_reddit(url: str) -> bool:
    return bool(_REDDIT_PATTERN.search(url))


# Build the thread .json endpoint (limit/depth query for comments). host overrides the
# netloc so the same thread can be retried on old.reddit.com as a fallback.
def reddit_json_url(url: str, host: str | None = None) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path.endswith(".json"):
        path = path[: -len(".json")]
    path += ".json"
    return urlunparse((parsed.scheme, host or parsed.netloc, path, "", "limit=50&depth=3", ""))


# Thread page URL without the .json suffix (used as Referer / page-render fallback).
def reddit_thread_url(url: str, host: str | None = None) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path.endswith(".json"):
        path = path[: -len(".json")]
    return urlunparse((parsed.scheme, host or parsed.netloc, path, "", "", ""))


# Parse Reddit listing JSON from raw text or minimal HTML wrapper.
def parse_reddit_json_payload(raw: str) -> list[Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("[") or text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, list) else None
    match = _PRE_JSON_RE.search(text)
    if match:
        try:
            data = json.loads(html_lib.unescape(match.group(1)).strip())
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, list) else None
    return None


# Format Reddit thread JSON as markdown (post + nested comments).
def reddit_data_to_markdown(data: list[Any], url: str) -> str:
    lines: list[str] = []
    try:
        post = data[0]["data"]["children"][0]["data"]
    except (IndexError, KeyError, TypeError):
        return f"Error: Unexpected Reddit response structure for {url}"
    lines.append(f"r/{post.get('subreddit','')} | u/{post.get('author','')} | score: {post.get('score',0)}")
    lines.append(f"# {post.get('title','')}")
    if post.get("selftext"):
        lines.append(post["selftext"])
    lines.append("")

    def _comments(children: list, depth: int = 0) -> None:
        for child in children:
            if child.get("kind") != "t1":
                continue
            child_data = child["data"]
            body = child_data.get("body", "").strip()
            if body and body != "[deleted]":
                lines.append(
                    "  " * depth
                    + f"[{child_data.get('author','?')} | +{child_data.get('score',0)}] {body}"
                )
            replies = child_data.get("replies")
            if isinstance(replies, dict):
                _comments(replies["data"]["children"], depth + 1)

    if len(data) > 1:
        _comments(data[1]["data"]["children"])

    return "\n".join(lines)[:15_000]


# Fetch thread JSON via curl_cffi TLS impersonation.
def _fetch_reddit_json_curl(json_url: str, thread_url: str, timeout: float) -> list[Any] | None:
    from curl_cffi import requests as _r

    resp = _r.get(
        json_url,
        impersonate="chrome124",
        timeout=max(5.0, timeout),
        headers={
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": thread_url,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else None


# Nav-cruft prefix pattern: lines before the real post body.
_NAV_END_RE = re.compile(
    r"(?:^|\n)(?:Go to \w|r/\w+)\n",
    re.MULTILINE,
)


# Strip Reddit's SPA header (Sign Up / Log In / Expand user menu / …) from inner_text.
def _strip_reddit_nav(text: str) -> str:
    m = _NAV_END_RE.search(text)
    return text[m.start() :].strip() if m else text.strip()


# Fetch the thread .json through the warm cloakbrowser and parse the listing payload.
# Chrome renders the JSON inside a <pre>, so the same parser used for curl handles it.
async def _fetch_reddit_json_browser(json_url: str, timeout: float) -> list[Any] | None:
    from core.fetch.browser.client import browser_fetch

    result = await browser_fetch(json_url, nav_timeout=max(float(timeout), 30.0), wait_sec=3.0)
    if not result.ok:
        logger.debug("reddit browser .json fetch failed for %s: %s", json_url, result.error or result.status)
        return None
    return parse_reddit_json_payload(result.html or "") or parse_reddit_json_payload(result.text or "")


# Fetch the rendered thread page via the warm cloakbrowser; return cleaned inner_text markdown.
async def _fetch_reddit_browser_page(thread_url: str, timeout: float) -> str | None:
    from core.fetch.browser.client import browser_fetch

    result = await browser_fetch(thread_url, nav_timeout=max(float(timeout), 30.0), wait_sec=5.0)
    if not result.ok or not result.text:
        logger.debug(
            "reddit browser page fetch failed for %s: %s", thread_url, result.error or result.status
        )
        return None

    text = _strip_reddit_nav(result.text)
    if len(text.strip()) < 200:
        logger.debug("reddit browser inner_text too short (%d chars) for %s", len(text), thread_url)
        return None
    return text


# Fetch a thread through a tiered fallback that degrades on antibot blocks:
#   1. curl_cffi .json (www)         — fast, no browser; Reddit increasingly 403s this
#   2. warm-browser .json (www)      — JSON behind the browser identity (clean structured md)
#   3. warm-browser .json (old)      — same on old.reddit.com (lighter, less guarded host)
#   4. warm-browser page (old)       — last resort: render old.reddit and strip nav cruft
async def fetch_reddit_json(url: str, timeout: float = 15.0) -> str:
    www_thread = reddit_thread_url(url)
    www_json = reddit_json_url(url)
    loop = asyncio.get_running_loop()

    # 1. curl_cffi .json — cheapest path when Reddit lets it through.
    try:
        data = await loop.run_in_executor(
            _io_pool,
            lambda: _fetch_reddit_json_curl(www_json, www_thread, timeout),
        )
        if data is not None:
            return reddit_data_to_markdown(data, url)
    except Exception as exc:
        logger.info("reddit curl_cffi json blocked for %s: %s — falling back to browser", www_json, exc)

    # 2. + 3. warm-browser .json, www then old.reddit (the antibot fallback).
    old_json = reddit_json_url(url, host="old.reddit.com")
    for json_url in (www_json, old_json):
        try:
            data = await _fetch_reddit_json_browser(json_url, timeout)
            if data is not None:
                return reddit_data_to_markdown(data, url)
        except Exception as exc:
            logger.info("reddit browser .json failed for %s: %s", json_url, exc)

    # 4. Last resort: render the old.reddit thread page and strip its nav header.
    try:
        text = await _fetch_reddit_browser_page(reddit_thread_url(url, host="old.reddit.com"), timeout)
        if text:
            return text
    except Exception as exc:
        logger.warning("reddit old.reddit page fetch failed for %s: %s", url, exc)

    return f"Error: Reddit fetch failed for {url}"


from custom_domains.base import FetchContext, PageResult

# Reddit needs room for curl_cffi + a warm-browser render of the thread page.
_REDDIT_READ_TIMEOUT_SEC = 60.0


# Unified handler: fetch a Reddit thread as JSON (curl_cffi → warm-browser in-page).
class RedditHandler:
    name = "reddit"
    fallback_to_generic = False
    scope = "read_page"  # browser/JSON path too slow for web_search inline parsing

    # True for Reddit thread comment URLs.
    def matches(self, url: str) -> bool:
        return is_reddit(url)

    # Fetch and format the thread; Reddit gets its own generous timeout floor.
    async def read(self, url: str, ctx: FetchContext) -> PageResult:
        timeout = max(float(ctx.timeout), _REDDIT_READ_TIMEOUT_SEC)
        markdown = await fetch_reddit_json(url, timeout=timeout)
        ok = bool(markdown) and not markdown.startswith("Error:")
        return PageResult(
            markdown=markdown or f"Error: Reddit fetch failed for {url}",
            ok=ok,
            method="reddit_json",
            apply_budget=ok,
            error="" if ok else (markdown or "reddit fetch failed"),
        )


HANDLER = RedditHandler()
