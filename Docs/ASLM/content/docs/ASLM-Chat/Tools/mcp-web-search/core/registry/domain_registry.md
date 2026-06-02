---
title: "domain_registry"
draft: false
---

## Module `domain_registry`

`Tools/mcp-web-search/core/registry/domain_registry.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\registry`. See **Related** for package index and callers.

---

## Classes

### `class PathWeight`

**Purpose:** Type `PathWeight` defined in `domain_registry.py`.

### `class DomainInfo`

**Purpose:** Type `DomainInfo` defined in `domain_registry.py`.

### `class AccessStrategy`

**Purpose:** Type `AccessStrategy` defined in `domain_registry.py`.

### `class DomainRegistry`

**Purpose:** Type `DomainRegistry` defined in `domain_registry.py`.

### `class _RegistryProxy`

**Purpose:** Type `_RegistryProxy` defined in `domain_registry.py`.

---

## Public functions

#### `def clear_domain_registry_cache() -> None`

**Purpose:** Clear cached merged registry and singleton (for tests).

#### `def load_domain_registry(profiles_dir, legacy_path) -> Dict[str, DomainInfo]`

**Purpose:** Return merged domain entries keyed by pattern.

**Steps:**

1. Return the computed result to the caller.

#### `def DomainRegistry.__init__(config_path, profiles_dir)`

**Purpose:** Load merged registry from profiles dir and optional legacy monolith.

#### `def DomainRegistry.lookup(url_or_domain) -> DomainInfo`

**Purpose:** Return DomainInfo preferring endpoint overlay when validated.

**Steps:**

1. Return the computed result to the caller.

#### `def DomainRegistry.resolve_access_strategy(url_or_domain) -> AccessStrategy`

**Purpose:** Resolve fetch strategy from overlay or static registry entry.

**Steps:**

1. Return the computed result to the caller.

#### `def DomainRegistry.needs_camoufox(url_or_domain) -> bool`

**Purpose:** True when resolved method is camoufox browser fetch.

#### `def DomainRegistry.prefers_nextjs_rsc(url_or_domain) -> bool`

**Purpose:** True when parsing_mode is nextjs_rsc for this domain.

#### `def DomainRegistry.summary() -> Dict[str, List[str]]`

**Purpose:** Group unique patterns by tier for operator reporting.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def DomainRegistry.loaded() -> bool`

**Purpose:** Implements `DomainRegistry.loaded` in `domain_registry.py`.

#### `def get_registry(config_path) -> DomainRegistry`

**Purpose:** Shared DomainRegistry singleton.

**Steps:**

1. Return the computed result to the caller.

#### `def _RegistryProxy.__getattr__(item)`

**Purpose:** Forward attribute lookup to get_registry() instance.

---

## Private functions

#### `def _merge_float_maps(existing, incoming, *, op) -> Dict[str, float]`

**Purpose:** Merge float maps with max or min per key.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _merge_path_weights(existing, incoming) -> List[PathWeight]`

**Purpose:** Merge path_weights lists; same prefix merges class_weights with max.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _parse_path_weights(raw) -> List[PathWeight]`

**Purpose:** Parse path_weights array from JSON into PathWeight objects.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _domain_from_dict(entry, defaults) -> Optional[DomainInfo]`

**Purpose:** Build DomainInfo from one profile or legacy JSON entry.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _merge_domain_info(base, overlay) -> DomainInfo`

**Purpose:** Merge two entries for the same pattern; overlay wins scalars, maps merge per policy.

**Steps:**

1. Return the computed result to the caller.

#### `def _validate_profile_file(path, data) -> None`

**Purpose:** Validate one domain profile JSON file structure.

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

#### `def _load_legacy_domains(path) -> Dict[str, DomainInfo]`

**Purpose:** Load domain patterns from legacy monolithic domain_registry.json.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _load_profile_domains(profiles_dir) -> Dict[str, DomainInfo]`

**Purpose:** Load and merge domain patterns from domain_profiles/ JSON files.

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

#### `def _load_merged_registry(profiles_dir_str, legacy_path_str) -> tuple[Dict[str, DomainInfo], bool, str]`

**Purpose:** Implements `_load_merged_registry` in `domain_registry.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def DomainRegistry._register_patterns(by_pattern) -> None`

**Purpose:** Register patterns and aliases into lookup map.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def DomainRegistry._extract_domain(url_or_domain) -> str`

**Purpose:** Normalize URL or host string to bare domain.

#### `def DomainRegistry._lookup_static(url_or_domain) -> DomainInfo`

**Purpose:** Lookup static DomainInfo without endpoint overlay.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def DomainRegistry._overlay_to_info(url_or_domain, overlay) -> DomainInfo`

**Purpose:** Build DomainInfo from static entry plus validated overlay strategy.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [registry/_index](../../../../_index/)
