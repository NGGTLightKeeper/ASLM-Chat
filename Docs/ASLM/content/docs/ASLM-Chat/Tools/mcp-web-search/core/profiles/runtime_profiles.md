---
title: "runtime_profiles"
draft: false
---

## Module `runtime_profiles`

`Tools/mcp-web-search/core/profiles/runtime_profiles.py` — ASLM Chat Python module.

---

## Classes

### `class RuntimeDomainProfiles`

**Purpose:** read_page can pick a known-good method up front instead of probing a fallback chain.

---

## Public functions

#### `def get_runtime_profiles() -> RuntimeDomainProfiles`

**Purpose:** Shared RuntimeDomainProfiles singleton.

#### `def RuntimeDomainProfiles.__init__(self, db_path) -> None`

**Purpose:** Open the SQLite store and apply the schema.

#### `def RuntimeDomainProfiles.record(self, url_or_domain, attempt) -> None`

**Purpose:** Record one fetch attempt against a domain, updating rolling per-method statistics.

#### `def RuntimeDomainProfiles.best_method(self, url_or_domain) -> ProfileHint | None`

**Purpose:** A hard override from known_domains wins while runtime confidence is still low.

---

## Related

- [profiles/_index](../_index/)
