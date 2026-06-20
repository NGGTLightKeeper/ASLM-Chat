---
title: "Reddit Parser and Web Cache Limits Update"
date: 2026-06-20T19:43:29Z
draft: false
description: "Fixes to Reddit thread fetching via a new tiered fallback chain, introduction of an orphaned browser temp profile reaper, and SQLite WAL size limits to prevent unbounded cache growth."
---

## New Features

- **[Web Search]**: Added a new tiered fallback chain for fetching Reddit threads to degrade gracefully on antibot blocks: attempts `curl_cffi` on www first, then warm-browser on www, followed by warm-browser on old.reddit.com, and finally a page render on old.reddit.com.
- **[Web Search]**: Introduced a `tempjanitor` to sweep and reap orphaned browser temp profiles leftover by crashes or force kills, which is invoked upon daemon startup.
- **[Documentation]**: Added new documentation for `core/fetch/browser` module including `daemon`, `identity_store`, and `tempjanitor`. Added documentation for `core/profiles/runtime_profiles` and tests for Reddit fallback logic (`test_reddit`).

## Bug Fixes

- **[Cache]**: Applied `PRAGMA journal_size_limit` to SQLite databases (hosted cache, source cache, identity store, and runtime profiles) to cap the `-wal` sidecar size and prevent it from growing unboundedly and filling disk space.
- **[Web Search]**: Removed stale SQLite cache files (`browser_identity.db-shm` and `browser_identity.db-wal`) that had grown unchecked.

## API Changes

- N/A

## Known Issues

- N/A
