from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse, urlunparse

from core.fetch.thread_pool import io_pool as _io_pool


_REDDIT_PATTERN = re.compile(r"reddit\.com/r/[^/]+/comments/")


def is_reddit(url: str) -> bool:
    return bool(_REDDIT_PATTERN.search(url))


async def fetch_reddit_json(url: str) -> str:
    loop = asyncio.get_running_loop()
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if not path.endswith(".json"):
        path += ".json"
    json_url = urlunparse((parsed.scheme, parsed.netloc, path, "", "limit=50&depth=3", ""))

    def _do() -> dict:
        from curl_cffi import requests as _r

        resp = _r.get(
            json_url,
            impersonate="firefox133",
            timeout=15,
            headers={
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        resp.raise_for_status()
        return resp.json()

    try:
        data = await loop.run_in_executor(_io_pool, _do)
    except Exception as exc:
        return f"Error: Reddit fetch failed: {exc}"

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
            data = child["data"]
            body = data.get("body", "").strip()
            if body and body != "[deleted]":
                lines.append("  " * depth + f"[{data.get('author','?')} | +{data.get('score',0)}] {body}")
            replies = data.get("replies")
            if isinstance(replies, dict):
                _comments(replies["data"]["children"], depth + 1)

    if len(data) > 1:
        _comments(data[1]["data"]["children"])

    return "\n".join(lines)[:15_000]
