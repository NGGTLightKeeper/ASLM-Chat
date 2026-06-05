---
title: "test_trust_registry_profiles"
draft: false
---

## Module `test_trust_registry_profiles`

`Tools/mcp-web-search/tests/test_trust_registry_profiles.py` — ASLM Chat Python module.

---

## Test methods

#### `def test_all_production_profile_json_parse() -> None`

**Purpose:** test_all_production_profile_json_parse — every modular profile has profile name and domains list.

**Steps:**

1. Iterate and transform or accumulate state.
2. Parse or serialize JSON payloads.

#### `def test_global_blacklist_and_tiers(tmp_path) -> None`

**Purpose:** test_global_blacklist_and_tiers — _global.json tiers and blocked_extensions apply.

#### `def test_merge_by_pattern_and_defaults(tmp_path) -> None`

**Purpose:** test_merge_by_pattern_and_defaults — later profile overrides tier; aliases and affinity merge.

#### `def test_defaults_applied_to_sparse_domain(tmp_path) -> None`

**Purpose:** test_defaults_applied_to_sparse_domain — profile defaults fill tier/cat on sparse domain rows.

#### `def test_legacy_fallback_when_profiles_empty(tmp_path) -> None`

**Purpose:** test_legacy_fallback_when_profiles_empty — empty profiles dir falls back to legacy monolith.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def test_profile_overrides_legacy_for_same_pattern(tmp_path) -> None`

**Purpose:** test_profile_overrides_legacy_for_same_pattern — modular profile wins over legacy for same pattern.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def test_production_registry_loads_from_legacy_monolith() -> None`

**Purpose:** test_production_registry_loads_from_legacy_monolith — TrustRegistry() resolves arxiv tier and pinterest block.

#### `def test_loader_cache_returns_same_object(tmp_path) -> None`

**Purpose:** test_loader_cache_returns_same_object — _load_merged_registry returns cached singleton.

---

## Private functions

#### `def _fresh_trust_cache() -> None`

**Purpose:** Implements `_fresh_trust_cache` in `test_trust_registry_profiles.py`.

#### `def _write_global(directory, *, tiers=…, blacklist=…) -> None`

**Purpose:** _write_global — write _global.json tiers/blacklist fixture.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def _write_profile(directory, name, *, profile, defaults=…, domains) -> None`

**Purpose:** _write_profile — write a minimal trust profile JSON fixture file.

**Steps:**

1. Parse or serialize JSON payloads.

---

## Related

- [tests/_index](../../../_index/)
