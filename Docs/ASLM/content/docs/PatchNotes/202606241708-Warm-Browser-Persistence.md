---
title: "Warm Browser Persistence"
date: 2026-06-24T17:08:18Z
draft: false
description: "Fixed a bug where the warm browser daemon was killed between tool calls. It now persists across calls and relies on an idle timeout for shutdown."
---

## New Features

- **[Documentation]**: Updated documentation for `mcp-web-search/core/config/settings.md`, `mcp-web-search/core/fetch/browser/client.md`, and `mcp-web-search/mcp-server.md` to reflect the new daemon persistence behavior and updated default timeout values.

## Bug Fixes

- **[MCP Web Search]**: Fixed an issue where the warm browser daemon was erroneously terminated when the tool call process exited. The daemon now outlives the client process that spawns it, ensuring it stays warm across multiple tool calls. It self-terminates based on `daemon_idle_shutdown_sec`, which was lowered from 30 minutes to 15 minutes (900.0s) to balance memory footprint with reuse.

## API Changes

- N/A

## Known Issues

- N/A
