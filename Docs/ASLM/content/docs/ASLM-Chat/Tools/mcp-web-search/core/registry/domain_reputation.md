---
title: "domain_reputation"
draft: false
---

## Module `domain_reputation`

`Tools/mcp-web-search/core/registry/domain_reputation.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\registry`. See **Related** for package index and callers.

---

## Classes

### `class DomainReport`

**Purpose:** Type `DomainReport` defined in `domain_reputation.py`.

### `class DomainReputationStore`

**Purpose:** Type `DomainReputationStore` defined in `domain_reputation.py`.

---

## Public functions

#### `def DomainReputationStore.__init__(db_path) -> None`

**Purpose:** Open or create reputation DB and mark static A/B domains protected.

#### `def DomainReputationStore.record(domain, query_type, score) -> None`

**Purpose:** Record one observation; updates per-type and global EMA, then re-evaluates decisions.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def DomainReputationStore.is_auto_blacklisted(domain) -> bool`

**Purpose:** True when domain_decisions marks domain auto_blacklisted.

**Steps:**

1. Return the computed result to the caller.

#### `def DomainReputationStore.get_reputation_score(domain, query_type) -> float`

**Purpose:** Best reputation in [0,1]: query-type EMA, else global EMA, else 0.50 neutral.

**Steps:**

1. Return the computed result to the caller.

#### `def DomainReputationStore.get_report(domain) -> Optional[DomainReport]`

**Purpose:** Build DomainReport for domain or None if no reputation rows exist.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def DomainReputationStore.get_promoted_tier(domain) -> Optional[str]`

**Purpose:** Return promoted trust tier (B/C) for domain if any.

#### `def DomainReputationStore.top_blacklisted(limit) -> list[dict]`

**Purpose:** List recently auto-blacklisted domains up to limit.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def DomainReputationStore.top_promoted(limit) -> list[dict]`

**Purpose:** List auto-promoted domains ordered by tier and promoted_at.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def get_reputation_store() -> DomainReputationStore`

**Purpose:** Lazily initialised global DomainReputationStore.

**Steps:**

1. Return the computed result to the caller.

#### `def domain_from_url(url) -> str`

**Purpose:** Extract bare hostname from URL, stripping www. prefix.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

---

## Private functions

#### `def DomainReputationStore._connect() -> sqlite3.Connection`

**Purpose:** Open SQLite connection with row factory and busy timeout.

**Steps:**

1. Return the computed result to the caller.

#### `def DomainReputationStore._init_db() -> None`

**Purpose:** Create tables and indexes from _SCHEMA_SQL.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def DomainReputationStore._protect_static_domains() -> None`

**Purpose:** Mark trust registry A/B tier patterns as protected from auto-blacklist.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def DomainReputationStore._upsert_ema(conn, domain, query_type, score, now) -> None`

**Purpose:** Insert or exponentially smooth-update one (domain, query_type) EMA row.

#### `def DomainReputationStore._evaluate_decisions(conn, domain, query_type) -> None`

**Purpose:** Apply auto-blacklist, un-blacklist, promote, and demote rules for domain.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def DomainReputationStore._upsert_decision(conn, domain, fields) -> None`

**Purpose:** Insert or patch domain_decisions row with given field updates.

**Steps:**

1. Iterate and transform or accumulate state.

---

## Related

- [registry/_index](../../../../_index/)
