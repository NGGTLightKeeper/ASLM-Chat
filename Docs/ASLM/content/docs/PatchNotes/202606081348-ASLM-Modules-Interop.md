---
title: "ASLM Modules Interop"
date: 2026-06-08T13:49:37Z
draft: false
description: "Updated API and UI views for ASLM Modules Interop, including support for external module tools, scoped tool registries, and stateless context compression endpoints."
---

## New Features

- **[ASLM Modules Interop]**: Added support for resolving tools and tool registries from external module directories, including loading module-specific `mcp.json` configurations.
- **[Context Compression]**: Added new endpoints (`/api/context_compression/decide/` and `/api/context_compression/build_event/`) for making context compression decisions and building compression timeline events from stateless overflow data, geared towards external module consumers.
- **[Generation Requests]**: Enhanced `generate_api` to accept and process `tool_sources` and `tool_context`, mapping tool server IDs to their source modules and enabling external module tools seamlessly in the main generation context.
- **[Documentation]**: Updated API documentation to reflect changes in `API/mcp.py`, `Apps/UI/views.py`, and `Settings/mcp_json.py` supporting ASLM Modules Interop.

## Bug Fixes

- N/A

## API Changes

- **[mcp.py]**: Added `tool_source_map` kwargs to tool execution and registry lookups, enabling targeted external module tool invocation (`get_server`, `list_servers`, `build_ollama_tools`, etc.).
- **[mcp_json.py]**: Added functions `mcp_json_signature_for` and `iter_user_mcp_entries_for` to parse configuration and generate signatures for specific external modules.
- **[views.py]**: Added `context_compression_decide_api` and `context_compression_build_event_api`.

## Known Issues

- N/A
