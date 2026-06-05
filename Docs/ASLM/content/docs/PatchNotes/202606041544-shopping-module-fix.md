---
title: "Shopping Module Fix"
date: 2026-06-04T15:44:00Z
draft: false
description: "Fixes to shopping module source handling and additions to shopping web integration testing documentation."
---

## New Features

- **[Documentation]**: Added documentation for `test_shopping_web_integration.py`, detailing integration tests for shopping web search functionality, effort limits, and citable search sources.

## Bug Fixes

- **[Web Search]**: Fixed preview generation in `_shopping_source_from_product` by preventing raw snippet text from leaking and updating lane labeling to "Source lane:". Tests were updated to verify these strict bounds and label corrections.

## API Changes

- N/A

## Known Issues

- N/A
