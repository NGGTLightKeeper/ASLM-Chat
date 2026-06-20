---
title: "New Chat Button Fix"
date: 2026-06-18T15:21:00Z
draft: false
description: "Fixes to the new chat button routing and updates to the chat controller documentation."
---

## New Features

- **[Documentation]**: Updated `chat-controller.md` to reflect the new signature for `startNewChat(pushState)`.

## Bug Fixes

- **[UI]**: Fixed the "New Chat" button so that when starting a new chat, the URL updates correctly via `history.pushState` to mirror the loadChat behavior if not already at the root `/`.
- **[UI]**: Updated the `startNewChat` function in `chat-controller.js` to accept a `pushState` parameter.
- **[UI]**: Updated `event-bindings.js` to pass `true` to `startNewChat` when the New Chat button is clicked.

## API Changes

- N/A

## Known Issues

- N/A
