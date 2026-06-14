---
title: "identity_store"
draft: false
---

## Module `identity_store`

`Tools/mcp-web-search/core/fetch/browser/identity_store.py` — ASLM Chat Python module.

---

## Classes

### `class IdentityStore`

**Purpose:** Type `IdentityStore` defined in `identity_store.py`.

---

## Public functions

#### `def get_identity_store() -> IdentityStore`

**Purpose:** Lazily-initialised process-wide IdentityStore singleton.

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `def _domain_matches(cookie_domain, host) -> bool`

**Purpose:** True when a stored cookie domain applies to the given host (lenient suffix match).

**Steps:**

1. Return the computed result to the caller.
