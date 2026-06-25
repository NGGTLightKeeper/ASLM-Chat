# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Deep onion search engine — article-link heuristic, extraction, and the parallel
search→scrape→BM25 flow, all offline (transport mocked, no Tor)."""

from __future__ import annotations

import asyncio

import core.fetch.onion.search as osearch
from core.fetch.onion.search import OnionResult, _extract_result_links, _is_article_path
from core.fetch.onion.transport import OnionFetch


def test_article_path_heuristic():
    assert _is_article_path("/en/some-press-freedom-story/a-77698587")    # DW article id
    assert _is_article_path("/world/2026/jun/25/some-slug")               # dated news path
    assert not _is_article_path("/en/top-stories/s-9097")                 # section, not article
    assert not _is_article_path("/search")                                # listing root
    assert not _is_article_path("/en")                                    # too shallow


_SEARCH_HTML = """
<html><body>
  <nav><a href="/en/top-stories/s-9097">Top stories</a>
       <a href="/sw/idhaa/s-11588">Swahili</a></nav>
  <div class="results">
    <a href="/en/press-freedom-under-pressure/a-77698587">Press freedom under pressure</a>
    <a href="/en/how-big-tech-changes-journalism/a-77696474">Big tech & journalism</a>
    <a href="https://www.dw.com/en/free-media-matters/a-77587540">Free media matters</a>
  </div>
</body></html>
"""

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


def test_extract_links_rewrites_to_onion_and_filters_nav():
    links = _extract_result_links(
        _SEARCH_HTML, onion_base="http://dwnews.onion",
        clearnet_host="dw.com", limit=10,
    )
    assert len(links) == 3                                   # 3 articles, nav/sections dropped
    assert all("dwnews.onion" in u for u in links)           # rewritten to onion host
    assert all("/a-" in u for u in links)
    assert not any("/s-" in u for u in links)                # sections excluded


def test_onion_search_flow(monkeypatch):
    async def fake_fetch(url, *, timeout=None, impersonate="chrome124"):
        html = _SEARCH_HTML if "/search" in url else _ARTICLE_HTML
        return OnionFetch(url=url, status="ok", ok=True, http_status=200, text=html)

    monkeypatch.setattr(osearch, "onion_fetch", fake_fetch)
    monkeypatch.setattr(osearch, "resolve_onion", lambda svc, **k: "http://dwnews.onion/en/")

    results = asyncio.run(osearch.onion_search(
        "press freedom", limit=3, per_link_timeout=5, max_chars=2000,
        concurrency=3, providers=("dw",),
    ))
    assert results and all(isinstance(r, OnionResult) for r in results)
    assert all(r.provider == "dw" and "dwnews.onion" in r.url for r in results)
    assert any("press freedom" in r.content.lower() for r in results)   # BM25 kept the topic
    assert all(r.content for r in results)


def test_onion_search_empty_when_no_links(monkeypatch):
    async def fake_fetch(url, *, timeout=None, impersonate="chrome124"):
        return OnionFetch(url=url, status="ok", ok=True, http_status=200,
                          text="<html><body><nav><a href='/en/x/s-1'>nav</a></nav></body></html>")

    monkeypatch.setattr(osearch, "onion_fetch", fake_fetch)
    monkeypatch.setattr(osearch, "resolve_onion", lambda svc, **k: "http://dwnews.onion/en/")
    results = asyncio.run(osearch.onion_search("x", providers=("dw",), per_link_timeout=5))
    assert results == []
