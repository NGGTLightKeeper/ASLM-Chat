---
title: "Probe Timeout and Startpage Docs"
date: 2026-06-14T19:11:46Z
draft: false
description: "Introduces probe timeout for circuit breaker health checks and adds documentation for Startpage engine backoff mechanism."
---

## New Features

- **[Documentation]**: Added module documentation for `startpage.py` detailing core flow, constants, and token caching/backoff mechanisms.
- **[Documentation]**: Added test documentation for `test_new_engine_parsers.py` covering tests for Startpage and other search engine integrations.

## Bug Fixes

- **[Search Core]**: Added a `PROBE_TIMEOUT` (60 seconds) to the circuit breaker's half-open state. This ensures that an abandoned half-open probe (e.g., due to deadline cancellation) is eventually expired, preventing the engine from being permanently locked out. Includes a new test `test_breaker_abandoned_probe_is_expired_not_wedged`.
- **[Search Core]**: Improved order-preserving deduplication for URLs in `prefetch.py` to ensure reliable scheduling.

## API Changes

- N/A

## Known Issues

- N/A
