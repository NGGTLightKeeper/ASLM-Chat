---
title: "api_keys"
draft: false
---

## Module `api_keys`

`Tools/mcp-web-search/core/config/api_keys.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\config`. See **Related** for package index and callers.

---

## Classes

### `class HostedSearchApiKeysSection`

**Purpose:** Type `HostedSearchApiKeysSection` defined in `api_keys.py`.

### `class SearchApiKeysSection`

**Purpose:** Type `SearchApiKeysSection` defined in `api_keys.py`.

### `class ApiKeysConfig`

**Purpose:** Type `ApiKeysConfig` defined in `api_keys.py`.

---

## Public functions

#### `def SearchApiKeysSection.tavily_api_key() -> str | None`

**Purpose:** Implements `SearchApiKeysSection.tavily_api_key` in `api_keys.py`.

#### `def SearchApiKeysSection.brave_api_key() -> str | None`

**Purpose:** Implements `SearchApiKeysSection.brave_api_key` in `api_keys.py`.

#### `def SearchApiKeysSection.serpapi_api_key() -> str | None`

**Purpose:** Implements `SearchApiKeysSection.serpapi_api_key` in `api_keys.py`.

#### `def load_api_keys(path) -> ApiKeysConfig`

**Purpose:** Load api_keys.json and cache an ApiKeysConfig singleton (custom path for tests only).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def reset_api_keys_cache() -> None`

**Purpose:** Drop the cached config (tests that rewrite api_keys.json).

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `def _read_nullable_str(raw, key) -> str | None`

**Purpose:** Read a nullable string from a JSON dict (blank → None).

**Steps:**

1. Return the computed result to the caller.

#### `def _bootstrap_api_keys_file(target) -> None`

**Purpose:** Create api_keys.json from the example template when missing.

**Steps:**

1. Handle errors and map them to a safe response.

---

## Related

- [config/_index](../../../../_index/)
