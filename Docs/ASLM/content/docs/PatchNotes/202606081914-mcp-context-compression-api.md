---
title: "MCP Tool Context and Context Compression APIs"
date: 2026-06-08T19:14:04Z
draft: false
description: "Introduced support for external MCP tool context mapping and new stateless context compression APIs."
---

## New Features

- **[Context Compression]**: Added new stateless APIs for deciding on context compression and building compression events for external modules (`api/context_compression/decide/` and `api/context_compression/build_event/`).
- **[External Tools Support]**: Added support for resolving and executing tools outside the core repository via new `tool_sources` and `tool_source_map` mechanisms.
- **[Documentation]**: Updated documentation for the MCP module, UI views, UI URLs, and MCP configuration settings to cover the new external tool capabilities and context compression stateless APIs.

## Bug Fixes

- N/A

## API Changes

- **[LLM API Services]**: Updated Google GenAI, LMS, Ollama, and OpenAI API callers to accept an optional `tool_source_map` to map tool server IDs to their source directories.
- **[MCP API]**: Expanded `list_servers`, `get_server`, and `build_ollama_tools` to accept `tools_dir` and `module_dir` keyword arguments.
- **[MCP Registry]**: Introduced scoped registry loading with `_ensure_registry_loaded_for` to cache servers based on their module paths.
- **[Settings]**: Added `mcp_json_signature_for` and `iter_user_mcp_entries_for` to `Settings/mcp_json.py` to handle configuration scoping.

## Known Issues

- N/A
