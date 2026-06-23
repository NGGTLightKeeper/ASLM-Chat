---
title: "Warm Browser Hard Timeouts"
date: 2026-06-23T11:01:11Z
draft: false
description: "Introduced hard timeouts for warm browser extraction and teardown processes to prevent infinite hangs, and updated related documentation."
---

## New Features

- **[MCP Web Search]**: Added hard caps (`_EXTRACT_TIMEOUT`, `_CLOSE_TIMEOUT`, `_TEARDOWN_TIMEOUT`) to warm browser extraction (`content()`, `evaluate()`, `title()`) and teardown processes in `daemon.py` to prevent wedged renderers or infinite scripts from holding the fetch lock indefinitely and stalling the daemon.
- **[Documentation]**: Added `test_browser_daemon.md` to document testing module functions and updated `daemon.md` with new timeout constants documentation.

## Bug Fixes

- **[MCP Web Search]**: Fixed an issue where a dead or hung browser page could hang the `close()` operation forever. The daemon now correctly bounds closing operations, flags wedged browsers for clean respawning, and rescues active cookies/storage safely before recycling the instance.

## API Changes

- N/A

## Known Issues

- N/A
