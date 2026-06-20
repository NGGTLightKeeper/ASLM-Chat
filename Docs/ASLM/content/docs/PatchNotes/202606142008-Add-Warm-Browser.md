---
title: "Add Warm Browser Logic"
date: 2026-06-14T20:08:55Z
draft: false
description: "Introduced persistent warm-browser daemon and client logic to the web search MCP tool, with corresponding documentation."
---

## New Features

- **[MCP Web Search]**: Introduced a persistent stealth-browser daemon (`daemon.py`) using `cloakbrowser` to serve page fetches warmly, avoiding cold-start costs.
- **[MCP Web Search]**: Added a client layer (`client.py`) that routes fetches dynamically between the new warm daemon and the legacy `camoufox` subprocess based on configuration.
- **[MCP Web Search]**: Implemented a persistent, family-keyed `IdentityStore` (`identity_store.py`) backed by SQLite to save and restore Playwright `storageState` (cookies, localStorage, etc.) across browser restarts.
- **[MCP Web Search]**: Extended `settings.py` with `BrowserSection` to configure the warm browser's backend, fallback behavior, memory limits, and recycle thresholds.
- **[MCP Web Search]**: Updated `web_search.py`'s inline parsing logic to skip parsing expensive domains (like `reddit.com`) and domains learned to be slow via the profile store, keeping them as snippet-only.
- **[Testing]**: Added offline coverage tests for the warm-browser layer (`test_browser_layer.py`), covering identity storage, configuration axes, and client dispatching.
- **[Testing]**: Added tests for the new inline-parse policy (read-page-only and learned-slow domains) in `test_search_core.py`.
- **[Documentation]**: Added generated documentation pages for the new browser modules (`client.md`, `daemon.md`, `identity_store.md`, `models.md`) and updated documentation for `settings.md`, `web_search.md`, and test modules.

## Bug Fixes

- N/A

## API Changes

- **[MCP Web Search]**: Added `browser` as a new method identifier in `core/profiles/models.py`. The method selector ranks it above HTTP methods but below the `camoufox` subprocess.

## Known Issues

- N/A
