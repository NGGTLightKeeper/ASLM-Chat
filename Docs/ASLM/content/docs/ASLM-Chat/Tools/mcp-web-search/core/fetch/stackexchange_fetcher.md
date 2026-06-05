---
title: "stackexchange_fetcher"
draft: false
---

## Module `stackexchange_fetcher`

`Tools/mcp-web-search/core/fetch/stackexchange_fetcher.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\fetch`. See **Related** for package index and callers.

---

## Public functions

#### `def stackexchange_question_id(url) -> str | None`

**Purpose:** Extract numeric question id from a /questions/{id}/ URL path.

#### `def is_stackexchange_question_url(url) -> bool`

**Purpose:** True when url is a supported Stack Exchange question page.

#### `def fetch_stackexchange_question_data_sync(url, timeout, answer_limit, comment_limit) -> dict[str, Any]`

**Purpose:** Fetch question + top answers via Stack Exchange API (sync).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def render_stackexchange_question_markdown(data) -> str`

**Purpose:** Render API payload as markdown for read_page / preview.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def fetch_stackexchange_question_sync(url, timeout, answer_limit) -> str`

**Purpose:** Sync fetch: API payload rendered as markdown.

#### `async def fetch_stackexchange_question_data(url, timeout, answer_limit, comment_limit) -> dict[str, Any]`

**Purpose:** Async wrapper around fetch_stackexchange_question_data_sync.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

#### `async def fetch_stackexchange_question(url, timeout, answer_limit) -> str`

**Purpose:** Async fetch: markdown for read_page / preview.

---

## Private functions

#### `def _host(url) -> str`

**Purpose:** Normalize host: lowercase, strip www.

#### `def _site_from_host(host) -> str | None`

**Purpose:** Map Stack Exchange hostname to API site parameter.

**Steps:**

1. Return the computed result to the caller.

#### `def _strip_html_fragment(fragment) -> str`

**Purpose:** Convert API HTML fragment to plain text (code blocks preserved as fenced).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _format_timestamp(value) -> str`

**Purpose:** Format Unix epoch as ISO-8601 UTC with Z suffix.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _stackexchange_api_get(url, timeout) -> dict[str, Any]`

**Purpose:** GET Stack Exchange API URL and return parsed JSON.

**Steps:**

1. Return the computed result to the caller.

#### `def _owner_name(item) -> str`

**Purpose:** Display name from API owner object.

#### `def _normalize_comment(item) -> dict[str, Any]`

**Purpose:** Normalize one comment item from API JSON.

**Steps:**

1. Return the computed result to the caller.

#### `def _normalize_answer(item, comments) -> dict[str, Any]`

**Purpose:** Normalize one answer item plus its comment list.

**Steps:**

1. Return the computed result to the caller.

#### `def _comments_by_post_id(items, id_field) -> dict[int, list[dict[str, Any]]]`

**Purpose:** Group comment items by post_id or parent id field.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

---

## Related

- [fetch/_index](../../../../_index/)
