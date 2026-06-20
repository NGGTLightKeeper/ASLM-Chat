---
title: "Update Requirements and Web Search Core"
date: 2026-06-15T11:29:40Z
draft: false
description: "Updated dependencies and modernized the web search stack by switching to a BM25 + CPU re-ranker and a warm cloakbrowser."
---

## New Features

- **[Core Settings]**: Updated `venv_requirements.json` dependencies and modified `first_run.py` to drop the heavy NLP/GLiNER stack (NLTK, spaCy) in favor of a BM25 and CPU decoder re-ranker setup for web search.
- **[MCP Web Search]**: Updated the eBay (`custom_domains/ebay.py`) and Reddit (`custom_domains/reddit.py`) custom domain fetchers to use the warm `cloakbrowser` daemon as the primary engine instead of the legacy `camoufox` and `patchright` subprocesses.
- **[Documentation]**: Updated documentation for `first_run.py`, `custom_domains/ebay.py`, and `custom_domains/reddit.py` to reflect the removal of the old NLP functions and the adoption of the warm `cloakbrowser`.

## Bug Fixes

- N/A

## API Changes

- N/A

## Known Issues

- N/A
