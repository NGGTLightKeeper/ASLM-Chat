---
title: "test_search_core"
draft: false
---

## Module `test_search_core`

`Tools/mcp-web-search/tests/test_search_core.py` — ASLM Chat Python module.

---

## Classes

### `class _Clock`

**Purpose:** Type `_Clock` defined in `test_search_core.py`.

#### Private Methods

- `def __call__() -> float`
  - **Purpose:** Execute __call__ logic.

### `class _FakeSerpApi`

**Purpose:** Replays a scripted event stream.

#### Public Methods

- `def search_stream(*args, **kwargs) -> Any`
  - **Purpose:** Execute search_stream logic.

---

## Public functions

#### `def test_lexical_word_boundary_no_substring_false_positive() -> Any`

**Purpose:** Test case for lexical word boundary no substring false positive.

#### `def test_hub_penalty_flags_category_pages() -> Any`

**Purpose:** Test case for hub penalty flags category pages.

#### `def test_skip_title_patterns() -> Any`

**Purpose:** Test case for skip title patterns.

#### `def test_year_policy_soft_only() -> Any`

**Purpose:** Test case for year policy soft only.

#### `def test_infer_query_language_scripts() -> Any`

**Purpose:** Test case for infer query language scripts.

#### `def test_triage_relevant_top_google_parses_immediately() -> Any`

**Purpose:** Test case for triage relevant top google parses immediately.

#### `def test_triage_skip_title_is_skipped() -> Any`

**Purpose:** Test case for triage skip title is skipped.

#### `def test_triage_consensus_upgrades_queued_source() -> Any`

**Purpose:** Test case for triage consensus upgrades queued source.

#### `def test_triage_google_startpage_one_family_vote() -> Any`

**Purpose:** Test case for triage google startpage one family vote.

#### `def test_breaker_error_opens_for_five_minutes() -> Any`

**Purpose:** Test case for breaker error opens for five minutes.

#### `def test_breaker_degradation_short_cooldown_and_recovery() -> Any`

**Purpose:** Test case for breaker degradation short cooldown and recovery.

#### `def test_breaker_failed_probe_backs_off_exponentially() -> Any`

**Purpose:** Test case for breaker failed probe backs off exponentially.

#### `def test_select_engines_low_default_pair() -> Any`

**Purpose:** Test case for select engines low default pair.

#### `def test_select_engines_low_falls_back_to_startpage() -> Any`

**Purpose:** Test case for select engines low falls back to startpage.

#### `def test_select_engines_low_never_empty() -> Any`

**Purpose:** Test case for select engines low never empty.

#### `def test_select_engines_medium_startpage_standby_when_google_open() -> Any`

**Purpose:** Test case for select engines medium startpage standby when google open.

#### `def test_web_search_medium_parses_winners_and_ranks(monkeypatch) -> Any`

**Purpose:** Test case for web search medium parses winners and ranks.

#### `def test_web_search_low_is_serp_only(monkeypatch) -> Any`

**Purpose:** Test case for web search low is serp only.

---

## Private functions

#### `def _ingest(session, *, engine, family, rank, url, title, snippet) -> Any`

**Purpose:** Execute _ingest logic.

#### `def _fake_reader(url, *, timeout, max_chars, focus, allow_browser) -> str`

**Purpose:** Execute _fake_reader logic.

---

## Related

- [_index](../_index/)
