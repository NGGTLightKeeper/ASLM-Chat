---
title: "harvester"
draft: false
---

## Module `harvester`

`Tools/mcp-web-search/core/fetch/onion/harvester.py` — ASLM Chat Python module.

---

## Public functions

#### `def load_anchor_candidates() -> tuple[str, ...]`

**Purpose:** Implements `load_anchor_candidates`.

#### `def harvest(store, anchors, timeout) -> dict[str, int]`

**Purpose:** Scan trusted clearnet anchors and upsert any that self-publish an onion.

---

## Private functions

#### `def _host(url) -> str`

**Purpose:** Implements `_host`.

#### `def _name_from_anchor(anchor) -> str`

**Purpose:** Implements `_name_from_anchor`.

#### `def _onion_location(anchor, timeout) -> str | None`

**Purpose:** Implements `_onion_location`.

---

## Related

- [onion/_index](../../_index/)
