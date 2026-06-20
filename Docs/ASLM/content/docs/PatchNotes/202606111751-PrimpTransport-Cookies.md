---
title: "Include Cookies in PrimpTransport"
date: 2026-06-11T17:52:18Z
draft: false
description: "Fixes PrimpTransport to include cookies in requests and adds documentation for transport modules."
---

## New Features

- **[Documentation]**: Added `transport.md` detailing the transport classes (`AiohttpTransport`, `PrimpTransport`, and `AdaptiveTransport`) and their methods.

## Bug Fixes

- **[Web Search]**: Fixed `PrimpTransport._fetch_sync` to properly include cookies in the request headers if they are provided in the `EngineRequest`.

## API Changes

- N/A

## Known Issues

- N/A
