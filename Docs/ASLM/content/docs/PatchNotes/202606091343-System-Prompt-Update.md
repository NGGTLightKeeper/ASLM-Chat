---
title: "System Instruction Update"
date: 2026-06-09T13:43:43Z
draft: false
description: "Updates to system prompts and web search tool descriptions to refine search query guidelines and effort levels."
---

## New Features

- **[System Prompt]**: Updated system instructions to prioritize `medium` search effort for ordinary research, shopping, and comparisons. Reserved `high` effort strictly for exhaustive or high-stakes tasks. Added instructions to answer immediately once sufficient evidence is found.

## Bug Fixes

- **[Web Search]**: Relaxed the query quality gate to permit a single natural intent word (e.g., "best") when paired with specific nouns and identifiers. Updated search instructions to avoid retrying with lower effort levels after exhausting `high` effort.

## API Changes

- **[Web Search]**: Updated schema descriptions for the web search tool to clarify the expected use cases and behaviors for `low`, `medium`, and `high` search effort levels.

## Known Issues

- N/A
