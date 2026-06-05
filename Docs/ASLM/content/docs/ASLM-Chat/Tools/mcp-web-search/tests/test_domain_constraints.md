---
title: "test_domain_constraints"
draft: false
---

## Module `test_domain_constraints`

`Tools/mcp-web-search/tests/test_domain_constraints.py` — ASLM Chat Python module.

---

## Test methods

#### `def test_user_boolean_or_is_preserved_with_site_constraint() -> None`

**Purpose:** parse_domain_constraints — preserve user OR when adding site: include.

#### `def test_domain_connector_or_is_removed_when_it_becomes_orphaned() -> None`

**Purpose:** parse_domain_constraints — drop orphaned OR between multiple site: includes.

#### `def test_exclude_only_site_constraint_is_sent_to_provider() -> None`

**Purpose:** parse_domain_constraints — exclude-only -site: passes through to provider query.

---

## Related

- [tests/_index](../../../_index/)
