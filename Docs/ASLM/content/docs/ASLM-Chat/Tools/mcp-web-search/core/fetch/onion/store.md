---
title: "store"
draft: false
---

## Module `store`

`Tools/mcp-web-search/core/fetch/onion/store.py` — ASLM Chat Python module.

---

## Classes

### `class OnionStore`

**Purpose:** Persistent store for auto-harvested onion services.

#### `def OnionStore.__init__(self, db_path) -> None`

**Purpose:** Implements `__init__`.

#### `def OnionStore._get_conn(self) -> sqlite3.Connection`

**Purpose:** Implements `_get_conn`.

#### `def OnionStore._init_db(self) -> None`

**Purpose:** Implements `_init_db`.

#### `def OnionStore.upsert(self, service) -> None`

**Purpose:** Implements `upsert`.

#### `def OnionStore.list_all(self) -> tuple[OnionService, ...]`

**Purpose:** Implements `list_all`.

#### `def OnionStore.age_of(self, name) -> float | None`

**Purpose:** Implements `age_of`.

---

## Public functions

#### `def get_onion_store() -> OnionStore`

**Purpose:** Implements `get_onion_store`.

---

## Related

- [onion/_index](../../_index/)
