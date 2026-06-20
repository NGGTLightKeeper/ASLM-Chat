---
title: "Regional Language Shopping Routing"
date: 2026-06-05T20:39:42Z
draft: false
description: "Introduces regional language routing to shopping search, adding new providers, improved parsing, and updated documentation."
---

## New Features

- **[MCP Web Search]**: Added regional language shopping routing, allowing the shopping search engine to prioritize specific providers based on language (e.g., Russian, Chinese, Japanese).
- **[MCP Web Search]**: Added new secondary shopping providers: `yandex_market`, `aliexpress`, `chinandex`, and `kakaku` to expand regional coverage and diversity.
- **[MCP Web Search]**: Extended `ShoppingSearchEngine` with language-specific limits, longer timeouts for regional queries, and logic to wait for regional primary providers.
- **[MCP Web Search]**: Improved product parser by adding support for JPY (¥). Also added heuristics to reject false-positive prices (like ratings disguised as Rubles) and filter out price-facet links.
- **[Testing]**: Added comprehensive unit tests for regional shopping routing preferences, language parameter propagation, wait logic for regional primary providers, and advanced price parsing features.
- **[Documentation]**: Updated documentation for the shopping core components (`engine.md`, `parse.md`, `providers.md`, `_shopping_worker.md`, `worker.md`, `web_search.md`) and added pages for the new test modules.

## Bug Fixes

- N/A

## API Changes

- N/A

## Known Issues

- N/A
