---
title: "Stateless Generate API"
date: 2026-06-08T11:14:26Z
draft: false
description: "Introduces a new stateless `/api/generate/` endpoint and updates corresponding documentation."
---

## New Features

- **[UI / API]**: Added a new stateless `/api/generate/` endpoint for external modules that streams LLM responses without persisting chat history or messages in the database.
- **[Documentation]**: Updated documentation for `views.py` to include the new `generate_api` handler and its helper functions (e.g., `_prepare_generation_request`, `_build_current_user_llm_entry`, `_build_generate_llm_messages`).
- **[Documentation]**: Added test documentation for `GenerateApiTests` in `tests.py`, detailing the coverage for the new stateless generation functionality.

## Bug Fixes

- N/A

## API Changes

- **[UI / API]**: Added `/api/generate/` as a new stateless endpoint. It accepts messages and options similarly to `/api/chat/`, but without creating or updating `Chat` and `Message` database records. It includes support for tool servers, history replay, context compression, and inline attachments.

## Known Issues

- N/A
