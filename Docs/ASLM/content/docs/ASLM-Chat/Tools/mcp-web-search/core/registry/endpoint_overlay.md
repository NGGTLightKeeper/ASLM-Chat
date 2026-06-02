---
title: "endpoint_overlay"
draft: false
---

## Module `endpoint_overlay`

`Tools/mcp-web-search/core/registry/endpoint_overlay.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\registry`. See **Related** for package index and callers.

---

## Classes

### `class ProbeCandidate`

**Purpose:** Type `ProbeCandidate` defined in `endpoint_overlay.py`.

### `class EndpointStrategy`

**Purpose:** Type `EndpointStrategy` defined in `endpoint_overlay.py`.

### `class EndpointOverlayStore`

**Purpose:** Type `EndpointOverlayStore` defined in `endpoint_overlay.py`.

---

## Public functions

#### `def normalize_domain(url_or_domain) -> str`

**Purpose:** Normalize a domain string from URL or bare host.

**Steps:**

1. Return the computed result to the caller.

#### `def normalize_path(url_or_domain) -> str`

**Purpose:** Normalize URL path; bare input treated as path on https host.

**Steps:**

1. Return the computed result to the caller.

#### `def ProbeCandidate.key() -> tuple`

**Purpose:** Build a stable deduplication key for this candidate.

**Steps:**

1. Return the computed result to the caller.

#### `def EndpointStrategy.method() -> str`

**Purpose:** Implements `EndpointStrategy.method` in `endpoint_overlay.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def EndpointStrategy.is_seed_only() -> bool`

**Purpose:** Implements `EndpointStrategy.is_seed_only` in `endpoint_overlay.py`.

#### `def build_probe_candidates(domain, sample_url) -> List[ProbeCandidate]`

**Purpose:** Build deduplicated probe candidates for a domain and optional sample URL.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def EndpointOverlayStore.__init__(db_path, promotion_success_count, deactivate_failure_count, recheck_ttl_sec)`

**Purpose:** Open overlay DB and ensure endpoint_overlay table exists.

#### `def EndpointOverlayStore.lookup_validated(domain, url) -> Optional[EndpointStrategy]`

**Purpose:** Return best validated EndpointStrategy for domain and optional URL path.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def EndpointOverlayStore.get_validated_seed_urls(domain) -> List[str]`

**Purpose:** List validated domain-scoped seed endpoint URLs for domain.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def get_endpoint_overlay(db_path) -> EndpointOverlayStore`

**Purpose:** Shared EndpointOverlayStore singleton (optional db_path override).

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `def _base_url_for_domain(domain) -> str`

**Purpose:** Build https base URL for a normalized domain.

#### `def _flatten_json(obj, depth, max_depth) -> str`

**Purpose:** Flatten nested JSON into plain text for content sniffing.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def EndpointOverlayStore._connect() -> sqlite3.Connection`

**Purpose:** Open SQLite connection with row factory.

#### `def EndpointOverlayStore._init_db() -> None`

**Purpose:** Create endpoint_overlay table if missing.

#### `def EndpointOverlayStore._fetch_existing(conn, candidate) -> Optional[sqlite3.Row]`

**Purpose:** Fetch existing overlay row matching probe candidate key.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [registry/_index](../../../../_index/)
