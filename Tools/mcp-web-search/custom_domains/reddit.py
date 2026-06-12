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


# Build the thread .json endpoint (limit/depth query for comments).
def reddit_json_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path.endswith(".json"):
        path = path[: -len(".json")]
    path += ".json"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "limit=50&depth=3", ""))


# Thread page URL without the .json suffix (used as Referer).
def reddit_thread_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path.endswith(".json"):
        path = path[: -len(".json")]
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


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


# Fetch the rendered thread page in a real browser, return cleaned inner_text markdown.
async def _fetch_reddit_camoufox_page(thread_url: str, timeout: float) -> str | None:
    from core.fetch.camoufox_fetcher import fetch_with_camoufox, is_camoufox_available

    if not is_camoufox_available():
        return None

    budget = max(float(timeout), 30.0)
    result = await fetch_with_camoufox(
        thread_url,
        wait_sec=5.0,
        timeout_sec=min(budget, 35.0),
        process_timeout=min(budget + 5.0, 45.0),
        warmup_count=0,
        normalize=False,
    )
    if not result.success or not result.inner_text:
        logger.debug("reddit camoufox page fetch failed for %s: %s", thread_url, result.error)
        return None

    text = _strip_reddit_nav(result.inner_text)
    if len(text.strip()) < 200:
        logger.debug("reddit camoufox inner_text too short (%d chars) for %s", len(text), thread_url)
        return None
    return text


# Fetch thread: curl_cffi JSON first, then camoufox browser render as fallback.
async def fetch_reddit_json(url: str, timeout: float = 15.0) -> str:
    thread_url = reddit_thread_url(url)
    json_url = reddit_json_url(url)
    loop = asyncio.get_running_loop()

    try:
        data = await loop.run_in_executor(
            _io_pool,
            lambda: _fetch_reddit_json_curl(json_url, thread_url, timeout),
        )
        if data is not None:
            return reddit_data_to_markdown(data, url)
    except Exception as exc:
        logger.info("reddit curl_cffi json blocked for %s: %s — trying camoufox", json_url, exc)

    try:
        text = await _fetch_reddit_camoufox_page(thread_url, timeout)
        if text:
            return text
    except Exception as exc:
        logger.warning("reddit camoufox page fetch failed for %s: %s", thread_url, exc)

    return f"Error: Reddit fetch failed for {url}"


from custom_domains.base import FetchContext, PageResult

# Reddit needs room for curl_cffi + a Camoufox browser session for the .json endpoint.
_REDDIT_READ_TIMEOUT_SEC = 60.0


# Unified handler: fetch a Reddit thread as JSON (curl_cffi → Camoufox in-page).
class RedditHandler:
    name = "reddit"
    fallback_to_generic = False

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
