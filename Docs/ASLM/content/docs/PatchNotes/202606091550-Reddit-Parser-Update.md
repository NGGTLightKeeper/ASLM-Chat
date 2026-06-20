---
title: "Reddit Parser Update"
date: 2026-06-09T15:50:33Z
draft: false
description: "Fixes to Reddit web search parsing to handle security blockers using an in-page JSON fetch via Camoufox, plus documentation updates."
---

## New Features

- **[Web Search]**: Added a Camoufox-based in-page JSON fetch mechanism (`fetch_page_json_with_camoufox`) that bypasses network security blockers by utilizing browser session cookies.
- **[Documentation]**: Added documentation for `test_read_page_reddit.py` and `test_reddit_fetch.py`, detailing the fallback logic and custom parsing for Reddit thread pages.

## Bug Fixes

- **[Web Search]**: Fixed Reddit JSON fetching to correctly fall back to Camoufox when `curl_cffi` encounters network security blockers instead of silently failing or dropping content.
- **[Web Search]**: Increased Reddit-specific page read timeouts to allow sufficient time for fallback behavior to complete.

## API Changes

- **[Internal]**: The `_ok` method in `_camoufox_worker.py` now supports a `payload_kind` argument.
- **[Internal]**: Replaced standalone thread JSON parsing with specific functions (`reddit_json_url`, `reddit_thread_url`, `parse_reddit_json_payload`, `reddit_data_to_markdown`) to improve maintainability.

## Known Issues

- N/A
