---
title: "Delete Camoufox and Migrate to Warm Browser Layer"
date: 2026-06-17T09:53:07Z
draft: false
description: "Removal of the Camoufox dependency from mcp-web-search and migration to the warm cloakbrowser daemon."
---

## New Features

- **[MCP Web Search]**: Removed the legacy Camoufox subprocess fallback from the web search tool, standardizing on the warm `cloakbrowser` daemon as the exclusive browser backend.
- **[MCP Web Search]**: Updated custom domain handlers (eBay, Reddit, dns-shop, etc.) to use the warm browser (`METHOD_BROWSER`) and removed the Camoufox engine path entirely.
- **[MCP Web Search]**: Added an explicit `shutdown_browser()` call to the `mcp-server.py` shutdown routine to ensure proper cleanup of the daemonized warm browser.
- **[Testing]**: Introduced `test_browser_daemon.py` for deterministic coverage of the warm-browser daemon's supervision logic, and refactored `test_browser_layer.py` to remove references to the legacy Camoufox backend.
- **[Documentation]**: Added generated documentation pages for the new `browser` module files (`client.md`, `daemon.md`, `models.md`) and tests, while removing outdated documentation for `camoufox_fetcher` and `_camoufox_worker`.

## Bug Fixes

- N/A

## API Changes

- **[MCP Web Search]**: The `browser_backend` configuration option was removed from `BrowserSection` in `core/config/settings.py` since `warm` is now the only supported backend.
- **[Profiles]**: The `METHOD_CAMOUFOX` fetch method identifier has been replaced with `METHOD_BROWSER` in `core/profiles/models.py` and `core/profiles/known_domains.py`.
- **[Dependencies]**: `camoufox` was removed from the `mcp-web-search` virtual environment requirements in `venv_requirements.json`. It is now only installed for the `mcp-browser-agent` virtual environment during first run bootstrap.

## Known Issues

- N/A
