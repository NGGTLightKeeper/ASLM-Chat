---
title: "test_domain_registry_profiles"
draft: false
---

## Module `test_domain_registry_profiles`

`Tools/mcp-web-search/tests/test_domain_registry_profiles.py` — ASLM Chat Python module.

---

## Test methods

#### `def test_all_production_profile_json_parse() -> None`

**Purpose:** test_all_production_profile_json_parse — every modular profile has profile name and domains list.

**Steps:**

1. Iterate and transform or accumulate state.
2. Parse or serialize JSON payloads.

#### `def test_merge_by_pattern_and_defaults(tmp_path) -> None`

**Purpose:** test_merge_by_pattern_and_defaults — later profile overrides tier/method; aliases and weights merge.

#### `def test_defaults_applied_to_sparse_domain(tmp_path) -> None`

**Purpose:** test_defaults_applied_to_sparse_domain — profile defaults fill tier/method on sparse domain rows.

#### `def test_class_weights_accessible_via_registry_lookup(tmp_path) -> None`

**Purpose:** test_class_weights_accessible_via_registry_lookup — lookup returns class_weights and parsing_mode.

#### `def test_json_api_hint_is_exposed_as_access_strategy_endpoint(tmp_path) -> None`

**Purpose:** test_json_api_hint_is_exposed_as_access_strategy_endpoint — json_api_hint becomes endpoint_url.

#### `def test_ncbi_host_does_not_use_pubmed_json_api() -> None`

**Purpose:** test_ncbi_host_does_not_use_pubmed_json_api — pubmed uses json_api; other ncbi hosts use http.

#### `def test_loader_cache_returns_same_object(tmp_path) -> None`

**Purpose:** test_loader_cache_returns_same_object — _load_merged_registry returns cached singleton.

#### `def test_legacy_fallback_when_profiles_empty(tmp_path) -> None`

**Purpose:** test_legacy_fallback_when_profiles_empty — empty profiles dir falls back to legacy monolith.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def test_profile_overrides_legacy_for_same_pattern(tmp_path) -> None`

**Purpose:** test_profile_overrides_legacy_for_same_pattern — modular profile wins over legacy for same pattern.

**Steps:**

1. Parse or serialize JSON payloads.

---

## Private functions

#### `def _fresh_registry_cache() -> None`

**Purpose:** Implements `_fresh_registry_cache` in `test_domain_registry_profiles.py`.

#### `def _write_profile(directory, name, *, profile, defaults=…, domains) -> None`

**Purpose:** _write_profile — write a minimal domain profile JSON fixture file.

**Steps:**

1. Parse or serialize JSON payloads.

---

## Related

- [tests/_index](../../../_index/)
