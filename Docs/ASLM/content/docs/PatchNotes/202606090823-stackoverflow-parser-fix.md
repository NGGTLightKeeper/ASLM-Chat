---
title: "StackOverflow Error Parser Fix"
date: 2026-06-09T08:23:58Z
draft: false
description: "Fixes to the StackOverflow error parser to properly handle rate limits, and updates to the test parsers and documentation."
---

## New Features

- **[Documentation]**: Added documentation for the `StackOverflow` class and `test_engine_parsers`, detailing how the API handles Stack Exchange IP rate limits by raising `RatelimitException`. Also added descriptions for various test methods verifying different search engines.

## Bug Fixes

- **[Web Search]**: Modified the `StackOverflow` web search engine to correctly handle API rate limits. It now catches HTTP 429 status codes or text indicating "too many requests", "temporarily rate limited", or "unusually high number of requests", explicitly raising a `RatelimitException` instead of a generic `DDGSException`.
- **[Testing]**: Updated `test_engine_parsers.py` to include `test_stackoverflow_reports_ip_block_as_rate_limit`, which verifies that the StackOverflow engine accurately detects IP blocks as rate limits and raises the appropriate exception.

## API Changes

- N/A

## Known Issues

- N/A
