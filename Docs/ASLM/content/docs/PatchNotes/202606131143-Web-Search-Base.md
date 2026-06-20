---
title: "Web Search Base Logic Update"
date: 2026-06-13T11:43:43Z
draft: false
description: "Implementation of base web search logic including query normalizer, various engine parsers, fetchers, and orchestrator with health and triage tracking."
---

## New Features

- **[MCP Web Search]**: Added a query normalizer (`query_normalizer.py`) for stripping multilingual stopwords and standardizing cache keys.
- **[MCP Web Search]**: Implemented parser integrations for multiple search engines including Brave, DuckDuckGo, Google, Qwant, Startpage, Yandex, and Yep, categorizing them by provider families.
- **[MCP Web Search]**: Added a headless browser fetcher utilizing Camoufox (`camoufox_fetcher.py`) with support for batches and complex JS-dependent academic sources.
- **[MCP Web Search]**: Established academic and scientific registry configuration (`academic_registry.json`) detailing countermeasures and retrieval patterns for various scientific aggregators.
- **[MCP Web Search]**: Introduced a health tracking system (`health.py`) incorporating circuit breaker logic to manage and restrict failing search engine endpoints.
- **[MCP Web Search]**: Implemented search quality scoring rules (`quality.py`) combining lexical matches, hub penalties, date signaling, and script inference logic.
- **[MCP Web Search]**: Created a robust `SerpApi` orchestrator (`serp_api.py`) with asynchronous streaming, limits, timeouts, and provider consensus voting.
- **[MCP Web Search]**: Added triage logic (`triage.py`) for real-time source evaluation, queue management, and upgrading URLs based on family consensus.
- **[MCP Web Search]**: Built the main orchestrator (`web_search.py`) handling streaming, evaluating triage priorities, and governing concurrency for eagerness-based parsing.
- **[Testing]**: Developed comprehensive offline coverage for the search core including quality evaluation, triage rules, health states, and orchestration (`test_search_core.py`).
- **[Documentation]**: Auto-generated comprehensive module documentation (`.md` files in `Docs/ASLM/content/docs/ASLM-Chat/Tools/mcp-web-search/`) covering the newly added engines, fetchers, search logic components, and testing procedures.

## Bug Fixes

- N/A

## API Changes

- N/A

## Known Issues

- N/A
