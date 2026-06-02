---
title: "aslm_embedding_bootstrap"
draft: false
---

## Module `aslm_embedding_bootstrap`

`Tools/mcp-web-search/core/query/aslm_embedding_bootstrap.py` — ASLM Chat Python module.

---

## Public functions

#### `def maybe_migrate_legacy_dirs() -> None`

**Purpose:** Rename legacy export dirs when the new names are not present yet.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def ensure_embedding_export(repo_id, local_dir) -> None`

**Purpose:** Download one HF repo into local_dir when the export is incomplete.

**Steps:**

1. Raise on invalid input or failure conditions.

#### `def ensure_aslm_embedding_models() -> None`

**Purpose:** Ensure encoder and decoder exports exist under Tools/mcp-web-search/models/.

---

## Private functions

#### `def _snapshot_download(repo_id, local_dir) -> None`

**Purpose:** Download HF snapshot (separate helper for tests).

---

## Related

- [query/_index](../../../../_index/)
