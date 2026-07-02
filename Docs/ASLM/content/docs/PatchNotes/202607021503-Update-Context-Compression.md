---
title: "Update Context Compression"
date: 2026-07-02T15:03:00Z
draft: false
description: "Updates to context compression including better fallback handling and moving tests into a dedicated module."
---

## New Features

- N/A

## Bug Fixes

- Fixed `Apps/UI/views.py` context compression to properly handle empty summaries to prevent replacing history with an empty summary.
- Improved `Tools/context_compression/history_compressor.py` semantic threshold logic to allow title-cased text with digits as real facts.
- Relocated test files (`build_fat_chat_summary.py`, `cache_chat_utils.py`, `run_live_fat_compression.py`) into `Tools/context_compression/tests/` for better isolation.
- Updated documentation in `Docs/ASLM/content/docs/ASLM-Chat/Tools/context_compression/` to reflect the new test module paths.

## API Changes

- N/A

## Known Issues

- N/A
