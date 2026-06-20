---
title: "Web Search Cache Update"
date: 2026-06-13T18:06:06Z
draft: false
description: "Introduces SQLite-backed payload cache, recency tracker, and background prefetching for web search, along with updated search testing and documentation."
---

## New Features

- **[Web Search]**: Added a SQLite-backed payload cache (`HostedSearchCache`) for complete web search result payloads with a flat TTL, and short negative TTL for empty result sets.
- **[Web Search]**: Implemented background prefetching (`PrefetchManager`) to crawl and cache raw HTML of top unparsed result URLs after a search for instant follow-up `read_page` access.
- **[Web Search]**: Introduced a recency tracker (`RecentSearchTracker`) to suppress immediately repeated identical queries (hard block) and prevent showing overlapping sources just served to the model within a short window.
- **[Web Search]**: Added logic to resolve direct PDF URLs (`_infer_pdf_url`) from result metadata or arXiv links.
- **[Documentation]**: Added documentation for the new web search cache modules: `hosted_cache`, `prefetch`, `recent_tracker`, and `test_search_cache`.

## Bug Fixes

- **[Web Search]**: Replaced legacy, untracked fire-and-forget prefetch logic with a disciplined, cancellable mechanism (`PrefetchManager`) using hard timeouts and concurrency limits.
- **[Web Search]**: Removed the dependency on the retired in-process query classifier, shifting from per-query-classification TTL to a consistent flat TTL for web search results.

## API Changes

- **[Web Search]**: Added configuration options `repeat_block_window_seconds`, `seen_source_window_seconds`, and `prefetch_max_urls` to the cache settings.
- **[Web Search]**: Updated `run_web_search` payload structure to conditionally include `cached`, `blocked`, `block_reason`, `note`, and `suppressed_seen` indicators based on recent query memory.

## Known Issues

- N/A
