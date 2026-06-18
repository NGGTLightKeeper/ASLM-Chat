---
title: "Delete Legacy Code"
date: 2026-06-18T16:55:07Z
draft: false
description: "Deletes legacy code from mcp-web-search, refactors content extraction, and updates associated documentation."
---

## New Features

- **[Web Search/Extraction]**: Replaced multiple profile-based chunk budgets with a single uniform `chunk_compaction.py` algorithm for scoring paragraphs. Replaced `profile_chunk_selector.py`.
- **[Web Search/Extraction]**: Introduced query-aware clause pruning using `micro_chunk_worker` inside `compress_read_page_markdown`.
- **[Web Search/Extraction]**: Implemented structural nav/UI rejection (menus, control clusters, link farms) within DOM block extraction to catch boilerplate that survives trafilatura.
- **[Web Search/Extraction]**: Refactored `hosted_providers.py` and `hosted_stream.py` to remove legacy properties (like timelimit options, region logic).
- **[Documentation]**: Added `_index.md` files for `core/search` and `core/read`, and relocated documentation for `service.py` and `web_search.py`.
- **[Documentation]**: Added comprehensive documentation for the new test modules (`test_chunk_compaction.py`, `test_content_cleaning.py`, `test_hosted_providers.py`, `test_search_core.py`).

## Bug Fixes

- **[Web Search/Core]**: The search query is now properly passed as the focus to the reader during search URL parsing for accurate chunk compaction.
- **[Web Search/Extraction]**: Fixed DOM block extraction structurally filtering blocks even if it matches clear prose.

## API Changes

- **[Web Search]**: `compress_read_page_markdown` and related reader tools now use the unified chunk compaction algorithm instead of complex profiles and models.
- **[Web Search/Providers]**: Removed `timelimit` argument from `HostedProvider.search` API methods. Providers now strictly respect standard max results.

## Known Issues

- N/A
