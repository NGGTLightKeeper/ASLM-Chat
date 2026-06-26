---
title: "test_onion_harvester"
draft: false
---

## Module `test_onion_harvester`

`Tools/mcp-web-search/tests/test_onion_harvester.py` — ASLM Chat Python module.

---

## Classes

### `class _Resp`

**Purpose:** Implements `_Resp`.

#### `def _Resp.__init__(self, headers)`

**Purpose:** Implements `__init__`.

### `class _FakeCurl`

**Purpose:** Implements `_FakeCurl`.

#### `def _FakeCurl.__init__(self, mapping)`

**Purpose:** Implements `__init__`.

#### `def _FakeCurl.get(self, url, **kw)`

**Purpose:** Implements `get`.

---

## Public functions

#### `def test_store_upsert_list_age(tmp_path)`

**Purpose:** Implements `test_store_upsert_list_age`.

#### `def test_harvest_disabled_is_noop(monkeypatch, tmp_path)`

**Purpose:** Implements `test_harvest_disabled_is_noop`.

#### `def test_harvest_admits_only_self_publishing(monkeypatch, tmp_path)`

**Purpose:** Implements `test_harvest_admits_only_self_publishing`.

#### `def test_harvest_skips_seed_covered_domains(monkeypatch, tmp_path)`

**Purpose:** Implements `test_harvest_skips_seed_covered_domains`.

#### `def test_registry_merges_store_with_seed_precedence(monkeypatch, tmp_path)`

**Purpose:** Implements `test_registry_merges_store_with_seed_precedence`.

---

## Private functions

#### `def _set_auto_expand(monkeypatch, on)`

**Purpose:** Implements `_set_auto_expand`.

---

## Related

- [tests/_index](../../_index/)
