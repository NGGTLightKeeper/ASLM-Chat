---
title: "Update Daemon Port and Refine Web-Search Cache"
date: 2026-06-20T15:10:40Z
draft: false
description: "Updated ASLM browser daemon port configurations, refined web-search query caching and query normalisation, and updated corresponding documentation."
---

## New Features

- **[Settings]**: Introduced `browser-daemon-port` (default `20004`) to `ASLM_Module.json` and `Settings/settings.py`, allowing ASLM to pass its chosen port to the web-search tool via `ASLM_BROWSER_DAEMON_PORT`.
- **[MCP Web Search]**: Cleaned up obsolete legacy search config options in `search_config.json` and `settings.py` related to DDGS, quality workers, and previews to simplify configuration.
- **[Documentation]**: Added new module map documentation and class/function details for the `core/read/` (including `service.py` for `read_page`) and `core/search/` (including `prefetch.py`) packages.

## Bug Fixes

- **[MCP Web Search]**: Addressed cache collisions for meaning-changing search operators (`site:`, `OR`, `-term`, `"exact"`) by ensuring they use a strict order-preserving cache key, while plain queries still share the token-sorted key.
- **[MCP Web Search]**: Updated `web_search.py` to correctly canonicalize URLs, deduplicating the same page from another family (e.g. `http`/`https`, trailing slash) to merge them into one source consensus vote.
- **[MCP Web Search]**: Prevented transient outages (e.g., all engines returning errors or timeouts) from incorrectly negative-caching as an empty SERP. Negative caches are now strictly applied only when at least one engine yields a genuine successful empty result.
- **[MCP Web Search]**: Improved query recency parsing to preserve older year dates acting as topic anchors (e.g., "Windows Server 2022") unless they are true recency indicators.
- **[MCP Web Search]**: Prevented search operators from incorrectly diluting lexical scores during extraction scoring.
- **[MCP Web Search]**: Fixed a shopping bug where 403/429 cooldowns were reset per-call. Shopping provider state (`ProviderState`) is now process-wide, ensuring timeouts persist across shopping queries.

## API Changes

- N/A

## Known Issues

- N/A
