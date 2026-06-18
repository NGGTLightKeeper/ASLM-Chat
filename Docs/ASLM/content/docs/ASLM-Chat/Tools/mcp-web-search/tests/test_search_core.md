---
title: "test_search_core"
draft: false
---

## Module `test_search_core`

`Tools/mcp-web-search/tests/test_search_core.py` — ASLM Chat Python module.

---

## Classes

### `class _Clock`

**Purpose:** Controlled clock for tests.

### `class _FakeSerpApi`

**Purpose:** Mocked SERP API for testing.

---

## Test methods

#### `def test_web_search_low_effort_no_parsers(monkeypatch) -> None`

**Purpose:** Low effort skips parsers entirely.

#### `def test_web_search_medium_parses_winners_and_ranks(monkeypatch) -> None`

**Purpose:** Medium effort runs parsers on top results.

#### `def test_web_search_passes_query_as_focus_to_reader(monkeypatch) -> None`

**Purpose:** Query string is passed to `read_page` as the focus for chunk compaction.

#### `def test_web_search_hosted_consensus_merges_not_overwrites(monkeypatch) -> None`

**Purpose:** Ensure hosted sources merge correctly without duplicating.

---

## Private functions

#### `async def _fake_reader(url, *, timeout=…, max_chars=…, focus=…, allow_browser=…) -> str`

**Purpose:** Mocked `read_page` implementation.

---

## Related

- [tests/_index](../../../_index/)
