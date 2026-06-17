---
title: "Update MCP Server and Add Read Page Tool"
date: 2026-06-17T10:34:12Z
draft: false
description: "Implementation of warm browser daemon, introduction of the read_page tool, dynamic venv package checking, and CPU-bound extraction offloading, along with documentation updates."
---

## New Features

- **[MCP Web Search]**: Introduced a `read_page` MCP tool to fetch one or more URLs and return clean markdown. It handles custom-domain handlers, anti-bot escalation to the warm browser, PDF extraction, and BM25 compression.
- **[MCP Web Search]**: Refactored the browser client and daemon for warm execution. The daemon now runs as a windowless background process, using `pythonw.exe` and `CREATE_NO_WINDOW` on Windows to prevent console windows from popping up.
- **[MCP Web Search]**: Updated the `read_page` service to offload CPU-bound HTML extraction (via trafilatura/lxml) to a thread pool executor, preventing long parses from blocking the `asyncio` event loop and enforcing deadlines.
- **[Core]**: Refactored `first_run.py` to dynamically provision browser binaries (Playwright, Camoufox) based on what each virtual environment's manifest declares (`_venv_declares`), rather than relying on a hardcoded tool list.
- **[Documentation]**: Added new documentation files mirroring the source paths for the warm browser package (`browser/_index.md`, `client.md`, `daemon.md`), `logging_setup.md`, and the `read` service (`read/_index.md`, `service.md`). Added or updated documentation for internal functions and new classes introduced in these modules.

## Bug Fixes

- **[MCP Web Search]**: Fixed logging for the windowless browser daemon by explicitly calling `setup_logging()` inside the daemon initialization.

## API Changes

- N/A

## Known Issues

- N/A
