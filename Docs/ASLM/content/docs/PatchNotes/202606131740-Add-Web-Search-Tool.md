---
title: "Add Web Search Tool"
date: 2026-06-13T17:40:24Z
draft: false
description: "Integration of the web search MCP tool, including documentation updates."
---

## New Features

- **[MCP Web Search]**: Added a new web search tool that runs multiple search engines (Google, Brave, DuckDuckGo, Yandex, Qwant, Yep, and Startpage) in parallel. It supports deduplication, ranking, and optional page parsing based on effort levels (`low`, `medium`, `high`).
- **[MCP Web Search]**: Added `search_io_logger.py` to record detailed tool IO events for the web search and read page services into a readable JSON array (`model_search_io.json`).
- **[MCP Web Search]**: Updated `mcp-server.py` to introduce the primary `web_search` tool for the model, alongside the raw `serp_search` tool. The primary tool offers ranked results with optional markdown parsing of the best pages.
- **[MCP Web Search]**: Updated logging in `logging_setup.py` and `web_search.py` to support new services (`services.web_search`, `trace.web_search`, `mcp.server`) and maintain backward compatibility.
- **[Documentation]**: Added generated documentation pages for search engines (`brave.md`, `duckduckgo.md`, `google.md`, `qwant.md`, `startpage.md`, `yandex.md`, `yep.md`), fetch profiles (`profiles.md`), read service (`service.md`), core runtime (`runtime.md`), and search tests (`test_search_core.md`).

## Bug Fixes

- N/A

## API Changes

- **[MCP Web Search]**: Exposed the `web_search` tool to the MCP adapter, which accepts `query`, `effort`, `region`, `safesearch`, and `timelimit` parameters.

## Known Issues

- N/A
