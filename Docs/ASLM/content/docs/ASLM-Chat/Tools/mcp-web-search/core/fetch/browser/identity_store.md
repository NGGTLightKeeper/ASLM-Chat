---
title: "identity_store"
draft: false
---

## Module `identity_store`

`Tools/mcp-web-search/core/fetch/browser/identity_store.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/fetch/browser`.

---

## Classes

### `class IdentityStore`

**Purpose:** Implements `IdentityStore`.

#### `def IdentityStore.__init__(self, db_path, max_generations) -> None`

**Purpose:** Implements `__init__`.

#### `def IdentityStore._get_conn(self) -> ...`

**Purpose:** Implements `_get_conn`.

#### `def IdentityStore._init_db(self) -> None`

**Purpose:** Implements `_init_db`.

#### `def IdentityStore.checkpoint(self, family, state, good) -> int`

**Purpose:** Implements `checkpoint`.

#### `def IdentityStore._prune(self, conn, family) -> None`

**Purpose:** Implements `_prune`.

#### `def IdentityStore._fetch_state(self, family, good_only) -> Optional[...]`

**Purpose:** Implements `_fetch_state`.

#### `def IdentityStore.latest_good(self, family) -> Optional[...]`

**Purpose:** Implements `latest_good`.

#### `def IdentityStore.latest(self, family) -> Optional[...]`

**Purpose:** Implements `latest`.

#### `def IdentityStore.rotate(self, family) -> Optional[...]`

**Purpose:** Implements `rotate`.

#### `def IdentityStore.cookies_for(self, family, host) -> list[...]`

**Purpose:** Implements `cookies_for`.

#### `def IdentityStore.cookie_header_for(self, family, host) -> str`

**Purpose:** Implements `cookie_header_for`.

#### `def IdentityStore.merge_set_cookie(self, owner, host, set_cookie_headers) -> None`

**Purpose:** Implements `merge_set_cookie`.

#### `def IdentityStore.http_cookies_map(self, owner, host) -> dict[...]`

**Purpose:** Implements `http_cookies_map`.

#### `def IdentityStore.http_cookie_header(self, owner, host) -> str`

**Purpose:** Implements `http_cookie_header`.

---

## Public functions

#### `def get_identity_store() -> IdentityStore`

**Purpose:** Implements `get_identity_store`.

---

## Private functions

#### `def _domain_matches(cookie_domain, host) -> bool`

**Purpose:** Implements `_domain_matches`.

---

## Related

- [browser/_index](../../_index/)
