---
title: "settings"
draft: false
---

## Module `settings`

`Tools/mcp-web-search/core/config/settings.py` — ASLM Chat Python module.

---

## Classes

### `class SearchSection`

**Purpose:** Type `SearchSection` defined in `settings.py`.

### `class ExtractionSection`

**Purpose:** Type `ExtractionSection` defined in `settings.py`.

### `class CacheSection`

**Purpose:** Type `CacheSection` defined in `settings.py`.

### `class QuerySection`

**Purpose:** Type `QuerySection` defined in `settings.py`.

### `class BrowserSection`

**Purpose:** Type `BrowserSection` defined in `settings.py`.

### `class TorSection`

**Purpose:** Type `TorSection` defined in `settings.py`.

### `class EffortSection`

**Purpose:** Type `EffortSection` defined in `settings.py`.



### `class BrowserSection`

**Purpose:** Warm-browser layer. Two independent axes: where the browser is allowed as a fallback (browser_fallback) and which backend serves it (browser_backend). The `daemon_idle_shutdown_sec` parameter defaults to 900.0 (15 minutes) to bound the life of the warm daemon.

### `class TorSection`

**Purpose:** Tor/onion access — the most optional thing in the search. OFF by default and strictly zero-install.

### `class SearchConfig`

**Purpose:** Type `SearchConfig` defined in `settings.py`.

---

## Public functions

#### `def load_search_config(path) -> SearchConfig`

**Purpose:** Load search_config.json and cache a SearchConfig singleton (custom path for tests only).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

---

## Private functions

#### `def _default_daemon_url() -> str`

**Purpose:** Return the default internal URL for the warm-browser daemon.

**Steps:**

1. Return the computed result to the caller.

#### `def _optional_string(value, default) -> Optional[str]`

**Purpose:** Coerce JSON values to optional strings (empty string → None).

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [config/_index](../../../../_index/)
