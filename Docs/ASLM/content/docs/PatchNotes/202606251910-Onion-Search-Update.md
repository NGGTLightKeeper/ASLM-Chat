---
title: "Update Onion Search Logic"
date: 2026-06-25T19:10:56Z
draft: false
description: "Updates to the MCP web search onion routing layer, moving to a static allowlist, SERP-scoped discovery, and zero-spawn Tor reusing."
---

## New Features

- **[Web Search]**: Onion search now uses multi-engine SERP-scoped discovery (`site:<host>`) to find article URLs on clearnet domains before rewriting the host to its onion mirror for Tor scraping. This replaces brittle per-site internal search paths.
- **[Web Search]**: Onion search runs now entirely bypass the hosted cache, repeat-block window, and recency tracker to prevent polluting plain search state.

## Bug Fixes

- **[Web Search]**: Removed error-prone Tor spawning lifecycle. The onion layer now strictly reuses an already-running Tor instance (system daemon on 9050, open Tor Browser on 9150, or an explicit `socks_url`) instead of attempting to discover and spawn its own binary.
- **[Web Search]**: Removed the anchored auto-expansion feature, harvester, and associated SQLite store. The onion allowlist is now exclusively a static, hand-vetted seed registry to reduce risk and complexity.

## API Changes

- **[Config]**: Removed `auto_expand`, `expand_refresh_hours`, `spawn_own`, `tor_binary`, `idle_shutdown_sec`, and `prewarm` from `TorSection` in `search_config.json` and `settings.py`.

## Known Issues

- N/A
