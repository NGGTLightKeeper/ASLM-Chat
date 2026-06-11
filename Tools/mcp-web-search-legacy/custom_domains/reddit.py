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


# Open thread HTML in Camoufox, then fetch .json in-page when curl_cffi is blocked.
async def _fetch_reddit_json_camoufox(thread_url: str, timeout: float) -> list[Any] | None:
    from core.fetch.camoufox_fetcher import fetch_page_json_with_camoufox, is_camoufox_available

    if not is_camoufox_available():
        return None

    budget = max(float(timeout), 25.0)
    result = await fetch_page_json_with_camoufox(
        thread_url,
        json_query="limit=50&depth=3",
        wait_sec=3.0,
        timeout_sec=min(budget - 10.0, 40.0),
        process_timeout=max(25.0, budget - 5.0),
        warmup_count=0,
    )
    if not result.success:
        logger.debug("reddit camoufox in-page json failed for %s: %s", thread_url, result.error)
        return None

    return parse_reddit_json_payload(result.html or result.inner_text)


# Fetch thread via .json suffix: curl_cffi first, then Camoufox on the same URL.
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
        data = await _fetch_reddit_json_camoufox(thread_url, timeout)
        if data is not None:
            return reddit_data_to_markdown(data, url)
    except Exception as exc:
        logger.warning("reddit camoufox json fetch failed for %s: %s", json_url, exc)

    return f"Error: Reddit fetch failed for {url}"
