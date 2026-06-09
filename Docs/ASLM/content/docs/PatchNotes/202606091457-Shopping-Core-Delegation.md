---
title: "Delegate Shopping Core Selection to LLM"
date: 2026-06-09T14:58:03Z
draft: false
description: "Delegated the activation of the shopping core to an explicit LLM-driven parameter instead of relying on automatic intent routing."
---

## New Features

- **[System Prompt]**: Updated the `SYSTEM_PROMPT.md` to explicitly instruct the model on how and when to use the `shopping=true` flag.
- **[MCP Web Search]**: Replaced automatic intent-based routing (`_should_run_shopping_core`) with an explicit boolean `shopping` parameter in the query schema. This requires the model to affirmatively set `shopping=true` when product search is desired.
- **[MCP Web Search]**: Plumbed the new `shopping` parameter through the MCP server layers, including the search query contract, fastmcp server adapter, classic mcp server bridge, and internal web search services.
- **[Testing]**: Updated integration tests (`test_shopping_web_integration.py`, `test_mcp_bridge_contract.py`, `test_search_query_contract.py`) to verify the new explicit parameter behavior and schema strictness.
- **[Documentation]**: Updated documentation to reflect the new `shopping` parameter and behavior across `search_query_contract`, `server.py`, `web_search.py` and relevant test documentation.

## Bug Fixes

- N/A

## API Changes

- Added `shopping` boolean argument to the web search schema and endpoints. Defaults to `false`.

## Known Issues

- N/A
