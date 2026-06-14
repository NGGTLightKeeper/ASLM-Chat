---
title: "models"
draft: false
---

## Module `models`

`Tools/mcp-web-search/core/fetch/browser/models.py` — ASLM Chat Python module.

---

## Constants

### `STATUS_OK`, `STATUS_BLOCKED`, `STATUS_TIMEOUT`, `STATUS_ERROR`, `STATUS_UNAVAILABLE`

Terminal fetch statuses. Mirrors the daemon contract; "unavailable" is added for the client side (daemon unreachable / warm browser disabled) so callers can tell a real block apart from "we never asked the browser".

## Classes

### `class BrowserFetch`

**Purpose:** Type `BrowserFetch` defined in `models.py`.
