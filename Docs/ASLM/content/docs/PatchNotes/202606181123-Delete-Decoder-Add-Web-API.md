---
title: "Delete Decoder and Add Web API Logic"
date: 2026-06-18T11:23:00Z
draft: false
description: "Replaced the legacy CPU decoder content-stage re-ranker with a new hosted search-API supplement layer."
---

## New Features

- **[MCP Web Search]**: Removed the CPU decoder content-stage re-ranker (legacy ASLM source-relevance model loader) and its associated configuration options from the pipeline modes and settings.
- **[MCP Web Search]**: Added a new optional hosted search-API supplement layer supporting Tavily, Firecrawl, Brave, and SerpApi (`api_keys.py`, `api_keys.json.example`, `hosted_providers.py`, `hosted_stream.py`).
- **[MCP Web Search]**: Updated `web_search.py` to interleave the new hosted search stream with the base scrape stream, supporting full page text pre-population and consensus voting.
- **[MCP Web Search]**: Updated `mcp_contract.py` effort tier documentation, modifying the 'high' effort description to reflect the removal of the extra relevance re-rank and highlight deeper parsing and a larger source pool.
- **[Testing]**: Removed `decoder_ranker` tests and added comprehensive unit tests for the new hosted providers and search core in `test_hosted_providers.py` and `test_search_core.py`.
- **[Dependencies]**: Removed unused neural and heavy dependencies from `venv_requirements.json`, including `huggingface_hub`, `numpy`, `safetensors`, `tokenizers`, `torch`, and `transformers`.
- **[Documentation]**: Updated generated documentation files in `Docs/ASLM/content/docs/ASLM-Chat/Tools/mcp-web-search/` to reflect the removal of `decoder_ranker.py` and `pipeline_modes.py`, and the addition of the new hosted API module documentation.

## Bug Fixes

- N/A

## API Changes

- N/A

## Known Issues

- N/A
