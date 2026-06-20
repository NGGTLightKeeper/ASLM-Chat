---
title: "Browser Daemon Port Collision Fix"
date: 2026-06-20T15:31:15Z
draft: false
description: "Resolves a port collision with ASLM's Ollama deployment by changing the default warm-browser daemon port."
---

## New Features

- **[MCP Web Search]**: Updated documentation for the web search core configuration and fetch modules, reflecting changes to the browser daemon setup (`client.md`, `daemon.md`, `settings.md`, etc.).

## Bug Fixes

- **[ASLM Settings]**: Changed the default port for the web-search warm browser daemon from `20004` to `20010` to avoid a collision with ASLM's Ollama service (`API/mcp.py`, `ASLM_Module.json`, `Settings/settings.py`).
- **[MCP Web Search]**: Updated default port configurations in `Tools/mcp-web-search/core/config/settings.py`, `Tools/mcp-web-search/core/fetch/browser/client.py`, and `Tools/mcp-web-search/core/fetch/browser/daemon.py` to use `20010`.

## API Changes

- N/A

## Known Issues

- N/A
