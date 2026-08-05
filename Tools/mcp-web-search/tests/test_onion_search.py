# Copyright NEXTGGTECH. Elastic License 2.0.

"""Deep onion search engine — article-link heuristic, SERP-scoped discovery with clearnet→
onion host rewrite, and the parallel discover→warm→scrape→BM25 flow, all offline (SERP and
Tor transport mocked, no network)."""

from __future__ import annotations

import asyncio

import core.fetch.onion.search as osearch
from core.fetch.onion.search import (
    OnionResult,
    _discover_for_service,
    _is_article_path,
)
from core.fetch.onion.models import OnionService
from core.fetch.onion.transport import OnionFetch


def test_article_path_heuristic():
    assert _is_article_path("/en/some-press-freedom-story/a-77698587")    # DW article id
    assert _is_article_path("/world/2026/jun/25/some-slug")               # dated news path
    assert not _is_article_path("/en/top-stories/s-9097")                 # section, not article
    assert not _is_article_path("/search")                                # listing root
    assert not _is_article_path("/en")                                    # too shallow


_DW = OnionService(
    name="dw", category="media",
    clearnet_anchor="https://www.dw.com/en/",
    onion="http://www.dwnews.onion/en/",
)

# A SERP result dict for site:dw.com — mixes article hits, a nav/section link, and an
# off-domain stray that must be dropped.
_FAKE_SERP = {
    "engines": {
        "ddg": {"sources": [
            {"url": "https://www.dw.com/en/press-freedom-under-pressure/a-77698587"},
            {"url": "https://www.dw.com/en/top-stories/s-9097"},          # section → dropped
            {"url": "https://www.dw.com/en/free-media-matters/a-77587540"},
            {"url": "https://evil.example/dw.com/phish/a-1"},             # off-domain → dropped
        ]},
        "brave": {"sources": [
            {"url": "https://www.dw.com/en/how-big-tech-changes-journalism/a-77696474"},
            {"url": "https://www.dw.com/en/press-freedom-under-pressure/a-77698587"},  # dup
        ]},
    }
}

_ARTICLE_HTML = """
<html><body><article><h1>Press freedom under pressure</h1>
<p>Press freedom is under growing pressure worldwide as governments tighten control over
independent media. Journalists face detention, surveillance and legal threats in many
countries, watchdog groups report. Analysts say the trend threatens democratic accountability
and the public's access to reliable information about press freedom and censorship.</p>
<p>This second paragraph adds further detail so the extractor has real body content to work
with, discussing press freedom, journalists, and censorship at sufficient length.</p>
</article></body></html>
"""


def test_discovery_rewrites_to_onion_and_filters(monkeypatch):
    async def fake_serp(query, **kw):
        assert query.startswith("site:dw.com ")
        return _FAKE_SERP

    monkeypatch.setattr(osearch, "run_serp_search", fake_serp, raising=False)
    monkeypatch.setattr(osearch, "resolve_onion", lambda svc, **k: "http://www.dwnews.onion/en/")

    pairs = asyncio.run(_discover_for_service(_DW, "press freedom", limit=10, serp_timeout=8))
    urls = [u for _, u in pairs]
    assert len(urls) == 3                                    # 3 unique articles
    assert all("dwnews.onion" in u for u in urls)            # rewritten to onion host
    assert all("/a-" in u for u in urls)
    assert not any("/s-" in u for u in urls)                 # sections excluded
    assert not any("evil.example" in u for u in urls)        # off-domain stray dropped
    assert all(name == "dw" for name, _ in pairs)


def _patch_serp(monkeypatch):
    async def fake_serp(query, **kw):
        return _FAKE_SERP
    monkeypatch.setattr(osearch, "run_serp_search", fake_serp, raising=False)


def test_onion_search_flow(monkeypatch):
    async def fake_fetch(url, *, timeout=None, impersonate="chrome124"):
        return OnionFetch(url=url, status="ok", ok=True, http_status=200, text=_ARTICLE_HTML)

    _patch_serp(monkeypatch)
    monkeypatch.setattr(osearch, "onion_fetch", fake_fetch)
    monkeypatch.setattr(osearch, "resolve_onion", lambda svc, **k: "http://www.dwnews.onion/en/")
    # tor is "available" without spawning anything real
    async def fake_warm(budget):
        return True
    monkeypatch.setattr(osearch, "_warm_tor", fake_warm)

    results = asyncio.run(osearch.onion_search(
        "press freedom", limit=3, per_link_timeout=5, max_chars=2000,
        concurrency=3, providers=("dw",),
    ))
    assert results and all(isinstance(r, OnionResult) for r in results)
    assert all(r.provider == "dw" and "dwnews.onion" in r.url for r in results)
    assert any("press freedom" in r.content.lower() for r in results)   # BM25 kept the topic
    assert all(r.content for r in results)


def test_onion_search_empty_when_tor_unavailable(monkeypatch):
    _patch_serp(monkeypatch)
    monkeypatch.setattr(osearch, "resolve_onion", lambda svc, **k: "http://www.dwnews.onion/en/")
    async def fake_warm(budget):
        return False                                          # tor down → no scraping
    monkeypatch.setattr(osearch, "_warm_tor", fake_warm)
    results = asyncio.run(osearch.onion_search("x", providers=("dw",), per_link_timeout=5))
    assert results == []


def test_onion_search_empty_when_no_candidates(monkeypatch):
    async def empty_serp(query, **kw):
        return {"engines": {"ddg": {"sources": [{"url": "https://www.dw.com/en/x/s-1"}]}}}
    monkeypatch.setattr(osearch, "run_serp_search", empty_serp, raising=False)
    monkeypatch.setattr(osearch, "resolve_onion", lambda svc, **k: "http://www.dwnews.onion/en/")
    results = asyncio.run(osearch.onion_search("x", providers=("dw",), per_link_timeout=5))
    assert results == []                                      # only a section link → nothing
