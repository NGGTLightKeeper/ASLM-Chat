---
title: "Support for Multiple Active Engines"
date: 2026-06-07T14:17:00Z
draft: false
description: "Introduces support for running multiple LLM engines simultaneously and allowing APIs to explicitly target enabled engines."
---

## New Features

- **[Engine Management]**: Enabled support for multiple active LLM engines. Runtimes for all enabled engines are now prepared, started, or warmed up simultaneously, removing the limitation of only preparing the globally active engine.
- **[Engine Synchronization]**: Introduced background synchronization of engine runtimes during application startup (in `UiConfig.ready()`) to prevent blocking Django initialization. Engine runtimes also dynamically sync whenever engine settings change.
- **[API Routing]**: Added support for specifying a target engine per-request via the `engine` query parameter or JSON body payload. Requests will now resolve and route to the specified engine as long as it is enabled in settings.
- **[Documentation]**: Updated documentation to reflect new multi-engine management functions (`sync_enabled_engine_runtimes`, `prepare_enabled_runtimes`, `cleanup_disabled_runtimes`) and API request resolution functions.

## Bug Fixes

- N/A

## API Changes

- **[UI Views API]**: Added `_resolve_request_engine` and `_resolve_request_engine_or_response` to handle explicit engine resolution from requests. Disabled engines explicitly requested will now return a 400 JSON error.
- **[UI Views API]**: Added a new exception `RequestEngineResolutionError` used when a request specifies an invalid or disabled engine.
- **[Engine Management API]**: Added `sync_enabled_engine_runtimes()`, `prepare_enabled_runtimes()`, and `cleanup_disabled_runtimes()` in `llm_api.py`. `handle_engine_transition` and `maybe_start_local_engine_service` now synchronize all enabled runtimes instead of only managing a single active engine.

## Known Issues

- N/A
