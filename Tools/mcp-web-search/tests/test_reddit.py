# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Reddit thread fetch: URL shaping, payload parsing, and the tiered fallback chain."""

from __future__ import annotations

import asyncio

import custom_domains.reddit as reddit

_THREAD = "https://www.reddit.com/r/codex/comments/1uaqzvk/again_we_are_here/"

# Minimal but realistic listing payload: one post + one comment with a nested reply.
_LISTING = [
    {"data": {"children": [{"data": {
        "subreddit": "codex", "author": "op", "score": 251,
        "title": "Again! We are here", "selftext": "body text",
    }}]}},
    {"data": {"children": [{"kind": "t1", "data": {
        "author": "alice", "score": 30, "body": "top comment",
        "replies": {"data": {"children": [{"kind": "t1", "data": {
            "author": "bob", "score": 3, "body": "nested reply", "replies": "",
        }}]}},
    }}]}},
]


# .json / page URLs honor a host override (so the old.reddit fallback hits the right host).
def test_url_host_override():
    assert reddit.reddit_json_url(_THREAD).startswith("https://www.reddit.com/")
    assert reddit.reddit_json_url(_THREAD).endswith(".json?limit=50&depth=3")
    assert reddit.reddit_json_url(_THREAD, host="old.reddit.com").startswith("https://old.reddit.com/")
    assert reddit.reddit_thread_url(_THREAD, host="old.reddit.com") == (
        "https://old.reddit.com/r/codex/comments/1uaqzvk/again_we_are_here"
    )


# A listing rendered into a <pre> (Chrome's JSON viewer) parses like a raw body.
def test_parse_payload_from_pre_wrapper():
    import json
    raw = f"<html><body><pre>{json.dumps(_LISTING)}</pre></body></html>"
    assert reddit.parse_reddit_json_payload(raw) == _LISTING


# Markdown carries the post header plus nested comments with author/score.
def test_markdown_shape():
    md = reddit.reddit_data_to_markdown(_LISTING, _THREAD)
    assert "u/op" in md and "score: 251" in md
    assert "# Again! We are here" in md
    assert "[alice | +30] top comment" in md
    assert "  [bob | +3] nested reply" in md  # nested one indent level deeper


# curl 403 → browser .json (www) succeeds and is parsed into structured markdown.
def test_fallback_curl_blocked_then_browser_json(monkeypatch):
    def _curl_blocked(*_a, **_k):
        raise RuntimeError("HTTP Error 403")

    calls: list[str] = []

    async def _browser_json(json_url, _timeout):
        calls.append(json_url)
        return _LISTING

    monkeypatch.setattr(reddit, "_fetch_reddit_json_curl", _curl_blocked)
    monkeypatch.setattr(reddit, "_fetch_reddit_json_browser", _browser_json)

    md = asyncio.run(reddit.fetch_reddit_json(_THREAD, timeout=5.0))
    assert "# Again! We are here" in md
    assert calls and "www.reddit.com" in calls[0]  # www .json tried first


# curl 403 + www browser block → old.reddit .json is the next rung and wins.
def test_fallback_old_reddit_json(monkeypatch):
    def _curl_blocked(*_a, **_k):
        raise RuntimeError("HTTP Error 403")

    seen: list[str] = []

    async def _browser_json(json_url, _timeout):
        seen.append(json_url)
        return _LISTING if "old.reddit.com" in json_url else None

    monkeypatch.setattr(reddit, "_fetch_reddit_json_curl", _curl_blocked)
    monkeypatch.setattr(reddit, "_fetch_reddit_json_browser", _browser_json)

    md = asyncio.run(reddit.fetch_reddit_json(_THREAD, timeout=5.0))
    assert "# Again! We are here" in md
    assert any("www.reddit.com" in u for u in seen) and any("old.reddit.com" in u for u in seen)
