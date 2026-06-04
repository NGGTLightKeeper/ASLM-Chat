---
title: "Merge Shopping Core With Web Search"
date: 2026-06-04T04:01:00Z
draft: false
description: "Integration of the shopping core into the web search MCP tool, including documentation updates."
---

## New Features

- **[MCP Web Search]**: Merged shopping core with the web search service. Added a dedicated asynchronous shopping worker (`_shopping_worker.py` and `worker.py`) to handle shopping queries via subprocess.
- **[MCP Web Search]**: Updated `web_search.py` to route search intents properly, evaluate whether to run the shopping core, set shopping limits based on search effort, and append strict JSON-structured shopping payloads directly into the primary neural model context.
- **[Testing]**: Added new integration tests in `test_shopping_web_integration.py` to verify shopping intent weighting, effort limits, product source citations, JSON schema strictness, and shopping context appends.
- **[Documentation]**: Added generated documentation pages for the new shopping core modules (`_shopping_worker.md`, `worker.md`), web search service (`web_search.md`), and tests (`test_shopping_web_integration.md`).

## Bug Fixes

- N/A

## API Changes

- N/A

## Known Issues

- N/A
