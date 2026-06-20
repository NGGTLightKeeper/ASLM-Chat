---
title: "OpenAI and Google GenAI Presets"
date: 2026-06-20T18:32:38Z
draft: false
description: "Adds preset support for OpenAI and Google GenAI models, including new data models, REST APIs, UI integration, and documentation."
---

## New Features

- **[Presets]**: Added preset configuration support for OpenAI models, scoped independently by endpoint URL and model name to avoid provider collisions.
- **[Presets]**: Added preset configuration support for Google GenAI (Gemini) models.
- **[UI]**: Updated engine adapters (`google-genai.js`, `openai.js`) and the engine manager to fully support the new preset configurations on the frontend.
- **[Documentation]**: Added new Python module documentation for `openai_presets` and `google_genai_presets`, updated existing models and UI documentation to reflect the new functionality.

## Bug Fixes

- N/A

## API Changes

- **[REST]**: Added `/api/openai_presets/*` endpoints for managing OpenAI presets (sync, select, create, rename, delete).
- **[REST]**: Added `/api/google_genai_presets/*` endpoints for managing Google GenAI presets (sync, select, create, rename, delete).

## Known Issues

- N/A
