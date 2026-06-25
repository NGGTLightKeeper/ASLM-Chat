---
title: "tor_proxy"
draft: false
---

## Module `tor_proxy`

`Tools/mcp-web-search/core/fetch/onion/tor_proxy.py` — ASLM Chat Python module.

---

## Public functions

#### `def mark_used() -> None`

**Purpose:** Record onion activity — resets the spawned tor's idle timer.

#### `def prewarm() -> None`

**Purpose:** Kick a background tor warmup.

#### `def discover_tor_binary(override) -> str | None`

**Purpose:** Locate an already-installed tor binary.

#### `def tor_health(socks_url, timeout) -> bool`

**Purpose:** Confirm a SOCKS url actually exits through Tor.

#### `def resolve_socks(force) -> str | None`

**Purpose:** Resolve (and cache) a usable tor SOCKS url.

---

## Private functions

#### `def _port_open(host, port, timeout) -> bool`

**Purpose:** Implements `_port_open`.

#### `def _tb_tail() -> Path`

**Purpose:** Implements `_tb_tail`.

#### `def _looks_like_tb_tor(path, leaf) -> bool`

**Purpose:** Implements `_looks_like_tb_tor`.

#### `def _indexer_lookup() -> str | None`

**Purpose:** Implements `_indexer_lookup`.

#### `def _scan_for_tor_browser(budget_sec) -> str | None`

**Purpose:** Implements `_scan_for_tor_browser`.

#### `def _spawn_tor(binary, bootstrap_timeout, idle_timeout) -> str | None`

**Purpose:** Implements `_spawn_tor`.

#### `def _reap_if_idle(idle_timeout) -> bool`

**Purpose:** Implements `_reap_if_idle`.

#### `def _start_idle_watch(idle_timeout) -> None`

**Purpose:** Implements `_start_idle_watch`.

#### `def _terminate() -> None`

**Purpose:** Implements `_terminate`.

---

## Related

- [onion/_index](../../_index/)
