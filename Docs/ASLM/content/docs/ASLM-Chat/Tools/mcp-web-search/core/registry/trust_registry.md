---
title: "trust_registry"
draft: false
---

## Module `trust_registry`

`Tools/mcp-web-search/core/registry/trust_registry.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\registry`. See **Related** for package index and callers.

---

## Classes

### `class TrustDomainEntry`

**Purpose:** Type `TrustDomainEntry` defined in `trust_registry.py`.

### `class _MergedTrustData`

**Purpose:** Type `_MergedTrustData` defined in `trust_registry.py`.

### `class TrustRegistry`

**Purpose:** Type `TrustRegistry` defined in `trust_registry.py`.

---

## Public functions

#### `def TrustDomainEntry.as_dict() -> dict[str, Any]`

**Purpose:** Serialize entry for legacy-compatible domain list output.

**Steps:**

1. Return the computed result to the caller.

#### `def clear_trust_registry_cache() -> None`

**Purpose:** Clear cached merged registry and singleton (for tests).

#### `def load_trust_registry(profiles_dir, legacy_path) -> tuple[dict[str, dict], dict, Dict[str, TrustDomainEntry]]`

**Purpose:** Return (tiers, blacklist, domains_by_pattern) from merged sources.

**Steps:**

1. Return the computed result to the caller.

#### `def TrustRegistry.__init__(path, profiles_dir) -> None`

**Purpose:** Load merged trust data from profiles, global config, and optional legacy file.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def TrustRegistry.get_entry(url) -> Optional[TrustDomainEntry]`

**Purpose:** Return trust entry for URL host if pattern matches.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def TrustRegistry.get_tier(url) -> Optional[str]`

**Purpose:** Return trust tier letter (A/B/C) for URL or None.

#### `def TrustRegistry.get_weight(url) -> float`

**Purpose:** Return numeric tier weight from tiers config for URL.

**Steps:**

1. Return the computed result to the caller.

#### `def TrustRegistry.is_blacklisted(url) -> bool`

**Purpose:** True when URL matches extension, domain, or pattern blacklist rules.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def TrustRegistry.filter_results(results, allowed_tiers) -> list`

**Purpose:** Keep search results whose URL tier is in allowed_tiers.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def get_trust_registry() -> TrustRegistry`

**Purpose:** Shared TrustRegistry singleton.

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `def _is_host_match(host, domain) -> bool`

**Purpose:** True when host equals domain or is a subdomain of it.

#### `def _merge_float_maps(existing, incoming) -> Dict[str, float]`

**Purpose:** Merge class_affinity maps keeping per-class maximum.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _entry_from_dict(entry, defaults) -> Optional[TrustDomainEntry]`

**Purpose:** Build TrustDomainEntry from one profile or legacy JSON entry.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _merge_trust_entry(base, overlay) -> TrustDomainEntry`

**Purpose:** Overlay wins scalars; aliases unioned; class_affinity max-merged.

**Steps:**

1. Return the computed result to the caller.

#### `def _validate_profile_file(path, data) -> None`

**Purpose:** Validate one trust profile JSON file structure.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Iterate and transform or accumulate state.

#### `def _profile_load_order(profiles_dir) -> List[Path]`

**Purpose:** Profile JSON load order from manifest.json then remaining *.json files.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _load_global_config(profiles_dir) -> tuple[dict[str, dict], dict]`

**Purpose:** Load tiers and blacklist from trust_registry_profiles/_global.json.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _load_legacy_domains(path) -> Dict[str, TrustDomainEntry]`

**Purpose:** Load domain patterns from legacy monolithic trust_registry.json.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _legacy_tiers_and_blacklist(path) -> tuple[dict[str, dict], dict]`

**Purpose:** Read tiers and blacklist from legacy monolith without loading domains.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _load_profile_domains(profiles_dir) -> Dict[str, TrustDomainEntry]`

**Purpose:** Load and merge domain patterns from trust_registry_profiles/ JSON files.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _resolve_legacy_path(explicit) -> Optional[Path]`

**Purpose:** Resolve legacy monolith path from explicit arg or known candidates.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _load_merged_registry(profiles_dir_str, legacy_path_str) -> _MergedTrustData`

**Purpose:** Implements `_load_merged_registry` in `trust_registry.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [registry/_index](../../../../_index/)
