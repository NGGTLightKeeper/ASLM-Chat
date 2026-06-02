---
title: "import_majestic"
draft: false
---

## Module `import_majestic`

`Tools/mcp-web-search/core/registry/import_majestic.py` — ASLM Chat Python module.

---

## Public functions

#### `def run(write, stats) -> None`

**Purpose:** Import Majestic Million CSV into trust_registry_profiles/majestic_web.json.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.
3. Parse or serialize JSON payloads.

#### `def main() -> int`

**Purpose:** CLI entry for Majestic Million import dry-run or --write.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _tier_for(ref_subnets) -> str | None`

**Purpose:** Map RefSubNets count to trust tier A/B/C or None if below minimum.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_csv(zip_path) -> io.TextIOWrapper`

**Purpose:** Open CSV text stream from majestic_million.zip.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def _existing_patterns() -> set[str]`

**Purpose:** Patterns already present in merged trust registry (profiles + monolith).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _blocked_fragments() -> list[str]`

**Purpose:** blocked_domain_contains fragments from merged trust blacklist.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _load_existing_output() -> list[dict]`

**Purpose:** Domain entries already written to majestic_web.json profile.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

---

## Related

- [registry/_index](../../../../_index/)
