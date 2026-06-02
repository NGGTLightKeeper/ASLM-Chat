---
title: "config"
draft: false
---

## Module `config`

`Tools/mcp-web-search/core/registry/config.py` — see source for implementation details.

---

## Module constants

#### `REGISTRY_DIR`

**Purpose:** Module constant `REGISTRY_DIR` (Path(__file__).resolve().parent…).

#### `PROJECT_ROOT`

**Purpose:** Module constant `PROJECT_ROOT` (REGISTRY_DIR.parents[1]…).

#### `CACHE_DIR`

**Purpose:** Module constant `CACHE_DIR` (PROJECT_ROOT / '_cache'…).

#### `TRUST_REGISTRY_PATH`

**Purpose:** Module constant `TRUST_REGISTRY_PATH` (REGISTRY_DIR / 'trust_registry.json'…).

#### `DOMAIN_REGISTRY_PATH`

**Purpose:** Module constant `DOMAIN_REGISTRY_PATH` (REGISTRY_DIR / 'domain_registry.json'…).

#### `DOMAIN_PROFILES_DIR`

**Purpose:** Module constant `DOMAIN_PROFILES_DIR` (REGISTRY_DIR / 'domain_profiles'…).

#### `TRUST_PROFILES_DIR`

**Purpose:** Module constant `TRUST_PROFILES_DIR` (REGISTRY_DIR / 'trust_registry_profiles'…).

#### `ACADEMIC_REGISTRY_PATH`

**Purpose:** Module constant `ACADEMIC_REGISTRY_PATH` (REGISTRY_DIR / 'academic_registry.json'…).

#### `DISCOVERED_ENDPOINTS_DB`

**Purpose:** Module constant `DISCOVERED_ENDPOINTS_DB` (str(CACHE_DIR / 'discovered_endpoints.db')…).

#### `ENDPOINT_PROBE_RECHECK_TTL_SEC`

**Purpose:** Module constant `ENDPOINT_PROBE_RECHECK_TTL_SEC` (86400…).

#### `ENDPOINT_PROMOTION_SUCCESS_COUNT`

**Purpose:** Module constant `ENDPOINT_PROMOTION_SUCCESS_COUNT` (2…).

#### `ENDPOINT_DEACTIVATE_FAILURE_COUNT`

**Purpose:** Module constant `ENDPOINT_DEACTIVATE_FAILURE_COUNT` (3…).

---

## Related

- [registry/_index](_index/)
