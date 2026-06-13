---
title: "Update bs4 Backend Parser"
date: 2026-06-13T18:09:08Z
draft: false
description: "Updated the default BeautifulSoup parser to use lxml when available."
---

## New Features

- N/A

## Bug Fixes

- **[Web Search]**: Updated `content_processor.py` and `dom_block_extractor.py` to use `lxml` as the default BeautifulSoup backend when available. This parser change provides roughly 1.6x faster parsing with the same bs4 API without requiring a new dependency, as `trafilatura` already depends on it.

## API Changes

- N/A

## Known Issues

- N/A
