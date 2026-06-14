---
title: "daemon"
draft: false
---

## Module `daemon`

`Tools/mcp-web-search/core/fetch/browser/daemon.py` — ASLM Chat Python module.

---

## Classes

### `class RecycleReason`

**Purpose:** Type `RecycleReason` defined in `daemon.py`.

### `class ScrapeResult`

**Purpose:** Type `ScrapeResult` defined in `daemon.py`.

### `class WarmChromium`

**Purpose:** Type `WarmChromium` defined in `daemon.py`.

### `class BrowserDaemon`

**Purpose:** Type `BrowserDaemon` defined in `daemon.py`.

---

## Private functions

#### `def _parse_proxy(proxy_url) -> Optional[str]`

**Purpose:** Parse a proxy URL into the cloakbrowser shape.

**Steps:**

1. Return the computed result to the caller.

#### `def _process_tree_rss_mb() -> float`

**Purpose:** Resident memory of this process plus its children (the chromium tree), in MB.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _serve(args) -> None`

**Purpose:** _serve defined in daemon.py

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _parse_args() -> argparse.Namespace`

**Purpose:** _parse_args defined in daemon.py

**Steps:**

1. Return the computed result to the caller.
