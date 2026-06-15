---
title: "Update Web Search Contract"
date: 2026-06-15T11:49:52Z
draft: false
description: "Re-architected the web search tool's search tiers, updated the browser daemon, and integrated a CPU decoder content-stage re-ranker, along with corresponding documentation updates."
---

## New Features

- **[MCP Web Search]**: Updated the `web_search.py` logic to redefine search tiers (`low`, `medium`, `high`) and their respective constraints. Removed the legacy GLiNER configuration from `settings.py`.
- **[MCP Web Search]**: Added a new CPU decoder content-stage re-ranker (`decoder_ranker.py`) for the `high` effort tier. It supports ModernBERT inference and blends neural relevance scores with the existing rules-based scores.
- **[Browser Backend]**: Modified `client.py` and `daemon.py` to enable lazy autostart of the warm browser daemon and added an idle-shutdown feature for improved resource management.
- **[Custom Domains]**: Refactored custom domain handlers (`base.py`, `ebay.py`, `reddit.py`, `x.py`, `youtube.py`) to classify specific sites (`SCOPE_READ_PAGE`) as too heavy for inline parsing, ensuring they remain snippet-only in search results to preserve performance.
- **[Testing]**: Updated and added several tests in `test_browser_layer.py` and `test_search_core.py` to cover the new custom domain rules, the decoder ranker, and the modified daemon behaviors.
- **[Documentation]**: Added and updated generated documentation pages to reflect changes in `settings.py`, `web_search.py`, `client.py`, `daemon.py`, `decoder_ranker.py`, and the updated testing and custom domain files.

## Bug Fixes

- N/A

## API Changes

- N/A

## Known Issues

- N/A
