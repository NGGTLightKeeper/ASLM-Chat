---
title: "identity_store"
draft: false
---

## Module `identity_store`

`Tools/mcp-web-search/core/fetch/browser/identity_store.py` — ASLM Chat Python module.

---

## Overview

Persistent, family-keyed browser identity store.

---

## Classes

### `class IdentityStore`

**Purpose:** Persistent per-family storageState store with generational good/burn backups.

---

## Public functions

#### `def get_identity_store() -> IdentityStore`

**Purpose:** Lazily-initialised process-wide IdentityStore singleton.

#### `def IdentityStore.__init__(self, db_path) -> None`

**Purpose:** Implements `IdentityStore.__init__` in `identity_store.py`.

#### `def IdentityStore.checkpoint(self, family, state) -> int`

**Purpose:** good=False marks a checkpoint that should not be restored as-is (e.g. burned).

#### `def IdentityStore.latest_good(self, family) -> Optional[dict[str, Any]]`

**Purpose:** Latest good storageState to seed a fresh browser on start / memory recycle.

#### `def IdentityStore.latest(self, family) -> Optional[dict[str, Any]]`

**Purpose:** Latest storageState regardless of good flag (diagnostics / forced restore).

#### `def IdentityStore.rotate(self, family) -> Optional[dict[str, Any]]`

**Purpose:** Used on a captcha/burn recycle so a poisoned identity is not restored.

#### `def IdentityStore.cookies_for(self, family) -> list[dict[str, Any]]`

**Purpose:** Cookies from the family's latest good state, optionally narrowed to a host.

#### `def IdentityStore.cookie_header_for(self, family, host) -> str`

**Purpose:** A ready "k=v; k2=v2" Cookie header for a host from the family's identity, or "".

#### `def IdentityStore.merge_set_cookie(self, owner, host, set_cookie_headers) -> None`

**Purpose:** A cookie with Max-Age<=0 (a deletion) removes the stored entry instead of adding it.

#### `def IdentityStore.http_cookies_map(self, owner, host) -> dict[str, str]`

**Purpose:** The owner's non-expired cookies for a host as {name: value} (newest write wins).

#### `def IdentityStore.http_cookie_header(self, owner, host) -> str`

**Purpose:** A ready "k=v; ..." Cookie header for a host from the owner's HTTP cookie history.

---

## Related

- [browser/_index](../_index/)
