# Copyright NEXTGGTECH. Elastic License 2.0.

"""Reddit thread fetch: URL shaping, markdown shaping, and the page-first fallback chain."""

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


# .json / page URLs honor a host override (so the old.reddit page path hits the right host).
def test_url_host_override():
    assert reddit.reddit_json_url(_THREAD).startswith("https://www.reddit.com/")
    assert reddit.reddit_json_url(_THREAD).endswith(".json?limit=50&depth=3")
    assert reddit.reddit_json_url(_THREAD, host="old.reddit.com").startswith("https://old.reddit.com/")
    assert reddit.reddit_thread_url(_THREAD, host="old.reddit.com") == (
        "https://old.reddit.com/r/codex/comments/1uaqzvk/again_we_are_here"
    )


# Markdown carries the post header plus nested comments with author/score.
def test_markdown_shape():
    md = reddit.reddit_data_to_markdown(_LISTING, _THREAD)
    assert "u/op" in md and "score: 251" in md
    assert "# Again! We are here" in md
    assert "[alice | +30] top comment" in md
    assert "  [bob | +3] nested reply" in md  # nested one indent level deeper


# old.reddit inner_text: nav head is cut at the post title, footer at the about/blog block.
def test_strip_old_reddit_nav_and_footer():
    raw = (
        "jump to content\nMY SUBREDDITS\nPOPULAR-ALL-USERS\nMORE »\n"
        "this post was submitted on 09 Apr 2026\n18 points (100% upvoted)\n"
        "Welcome to Reddit.\n\n18\n\n"
        "Anyone here tried Hermes Agent?Discussion (self.Rag)\n\n"
        "submitted 2 months ago by marwan_rashad5\n"
        "post body\n\n[–]alice 1 point 2 months ago\ntop comment\n"
        "permalinkembedsavereportreply\n"
        "about\nblog\nabout\nadvertising\ncareers\n"
        "Use of this site constitutes acceptance of our User Agreement.\n"
        "Reddit uses cookies and similar technologies to:\nCONTINUE"
    )
    text = reddit._strip_reddit_nav(raw)
    assert text.startswith("Anyone here tried Hermes Agent?")
    assert "top comment" in text
    assert "jump to content" not in text and "MY SUBREDDITS" not in text
    assert "advertising" not in text and "CONTINUE" not in text


# The old.reddit page render goes first; when it succeeds the .json API is never touched.
def test_page_first_json_untouched(monkeypatch):
    page_urls: list[str] = []

    async def _page_ok(thread_url, _timeout):
        page_urls.append(thread_url)
        return "r/codex\npost body rendered from old.reddit"

    def _curl_must_not_run(*_a, **_k):
        raise AssertionError(".json API must not be called when the page render succeeds")

    monkeypatch.setattr(reddit, "_fetch_reddit_browser_page", _page_ok)
    monkeypatch.setattr(reddit, "_fetch_reddit_json_curl", _curl_must_not_run)

    md = asyncio.run(reddit.fetch_reddit_json(_THREAD, timeout=5.0))
    assert "post body rendered from old.reddit" in md
    assert page_urls and "old.reddit.com" in page_urls[0]


# Page render failed (browser down / too short) → the .json API rung wins.
def test_fallback_json_api(monkeypatch):
    async def _page_dead(*_a, **_k):
        return None

    json_urls: list[str] = []

    def _curl_ok(json_url, _thread_url, _timeout):
        json_urls.append(json_url)
        return _LISTING

    monkeypatch.setattr(reddit, "_fetch_reddit_browser_page", _page_dead)
    monkeypatch.setattr(reddit, "_fetch_reddit_json_curl", _curl_ok)

    md = asyncio.run(reddit.fetch_reddit_json(_THREAD, timeout=5.0))
    assert "# Again! We are here" in md
    assert json_urls and json_urls[0].endswith(".json?limit=50&depth=3")


# Both rungs blocked → explicit error marker (handler flips ok=False on it).
def test_all_rungs_blocked(monkeypatch):
    async def _page_dead(*_a, **_k):
        raise RuntimeError("browser daemon unavailable")

    def _curl_blocked(*_a, **_k):
        raise RuntimeError("HTTP Error 429")

    monkeypatch.setattr(reddit, "_fetch_reddit_browser_page", _page_dead)
    monkeypatch.setattr(reddit, "_fetch_reddit_json_curl", _curl_blocked)

    md = asyncio.run(reddit.fetch_reddit_json(_THREAD, timeout=5.0))
    assert md.startswith("Error:")
