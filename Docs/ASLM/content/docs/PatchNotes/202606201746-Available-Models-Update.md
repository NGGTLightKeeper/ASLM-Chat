---
title: "Update Available Models Logic and UI"
date: 2026-06-20T17:46:16Z
draft: false
description: "Updated logic for getting and refreshing available models, especially for LM Studio JIT loading, and tweaked engine API key UI."
---

## New Features

- **[Core]**: Enhanced LM Studio model handling to leverage just-in-time (JIT) loading. The system now lists all downloaded models, rather than only pre-loaded ones, allowing automatic JIT loading when generation or capability inspection is requested.
- **[UI]**: Generalized the model list polling mechanism to support all engines, rather than only LM Studio.
- **[UI]**: Improved the engine API key settings UI, removing the on/off toggle for engines that always require an API key (like Gemini) and fixing the endpoint configuration for Google GenAI.
- **[API]**: Added support for a `refresh` parameter in the model list API to force a cache bypass and re-probe available models.
- **[Documentation]**: Added generated documentation pages reflecting the updated function signatures and UI routines.

## Bug Fixes

- N/A

## API Changes

- N/A

## Known Issues

- N/A
