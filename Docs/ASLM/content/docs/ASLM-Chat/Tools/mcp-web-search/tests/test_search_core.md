---
title: "test_search_core"
draft: false
---

## Module `test_search_core`

`Tools/mcp-web-search/tests/test_search_core.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/tests`.

---

## Classes

### `class _Clock`

**Purpose:** Implements `_Clock`.

#### `def _Clock.__init__(self) -> None`

**Purpose:** Implements `__init__`.

#### `def _Clock.__call__(self) -> float`

**Purpose:** Implements `__call__`.

### `class _FakeSerpApi`

**Purpose:** Replays a scripted event stream.

#### `def _FakeSerpApi.__init__(self, *args, **kwargs) -> None`

**Purpose:** Implements `__init__`.

#### `async def _FakeSerpApi.search_stream(self, *args, **kwargs)`

**Purpose:** Implements `search_stream`.

---

## Public functions

#### `def test_lexical_word_boundary_no_substring_false_positive()`

**Purpose:** Implements `test_lexical_word_boundary_no_substring_false_positive`.

#### `def test_hub_penalty_flags_category_pages()`

**Purpose:** Implements `test_hub_penalty_flags_category_pages`.

#### `def test_skip_title_patterns()`

**Purpose:** Implements `test_skip_title_patterns`.

#### `def test_year_policy_soft_only()`

**Purpose:** Implements `test_year_policy_soft_only`.

#### `def test_infer_query_language_scripts()`

**Purpose:** Implements `test_infer_query_language_scripts`.

#### `def test_triage_relevant_top_google_parses_immediately()`

**Purpose:** Implements `test_triage_relevant_top_google_parses_immediately`.

#### `def test_triage_skip_title_is_skipped()`

**Purpose:** Implements `test_triage_skip_title_is_skipped`.

#### `def test_triage_consensus_upgrades_queued_source()`

**Purpose:** Implements `test_triage_consensus_upgrades_queued_source`.

#### `def test_triage_google_startpage_one_family_vote()`

**Purpose:** Implements `test_triage_google_startpage_one_family_vote`.

#### `def test_breaker_error_opens_for_five_minutes()`

**Purpose:** Implements `test_breaker_error_opens_for_five_minutes`.

#### `def test_breaker_degradation_short_cooldown_and_recovery()`

**Purpose:** Implements `test_breaker_degradation_short_cooldown_and_recovery`.

#### `def test_breaker_failed_probe_backs_off_exponentially()`

**Purpose:** Implements `test_breaker_failed_probe_backs_off_exponentially`.

#### `def test_breaker_abandoned_probe_is_expired_not_wedged()`

**Purpose:** Implements `test_breaker_abandoned_probe_is_expired_not_wedged`.

#### `def test_pacing_holds_engine_within_min_interval()`

**Purpose:** Implements `test_pacing_holds_engine_within_min_interval`.

#### `def test_pacing_skipped_for_tolerant_engines()`

**Purpose:** Implements `test_pacing_skipped_for_tolerant_engines`.

#### `def test_select_engines_low_default_pair()`

**Purpose:** Implements `test_select_engines_low_default_pair`.

#### `def test_select_engines_low_falls_back_to_startpage()`

**Purpose:** Implements `test_select_engines_low_falls_back_to_startpage`.

#### `def test_select_engines_low_never_empty()`

**Purpose:** Implements `test_select_engines_low_never_empty`.

#### `def test_select_engines_medium_startpage_standby_when_google_open()`

**Purpose:** Implements `test_select_engines_medium_startpage_standby_when_google_open`.

#### `def test_custom_domain_scope_marks_browser_heavy_readpage_only()`

**Purpose:** Implements `test_custom_domain_scope_marks_browser_heavy_readpage_only`.

#### `def test_inline_parse_blocks_readpage_only_handler()`

**Purpose:** Implements `test_inline_parse_blocks_readpage_only_handler`.

#### `def test_inline_parse_skips_learned_slow_domain(monkeypatch)`

**Purpose:** Implements `test_inline_parse_skips_learned_slow_domain`.

#### `def test_inline_parse_allows_unknown_domain()`

**Purpose:** Implements `test_inline_parse_allows_unknown_domain`.

#### `def test_web_search_medium_parses_winners_and_ranks(monkeypatch)`

**Purpose:** Implements `test_web_search_medium_parses_winners_and_ranks`.

#### `def test_web_search_passes_query_as_focus_to_reader(monkeypatch)`

**Purpose:** Implements `test_web_search_passes_query_as_focus_to_reader`.

#### `def test_web_search_hosted_consensus_merges_not_overwrites(monkeypatch)`

**Purpose:** Implements `test_web_search_hosted_consensus_merges_not_overwrites`.

#### `def test_web_search_low_is_serp_only(monkeypatch)`

**Purpose:** Implements `test_web_search_low_is_serp_only`.

---

## Private functions

#### `def _ingest(session, engine, family, rank, url, title, snippet)`

**Purpose:** Implements `_ingest`.

#### `async def _fake_reader(url, timeout, max_chars, focus, allow_browser) -> str`

**Purpose:** Implements `_fake_reader`.

---

## Related

- [tests/_index](../../_index/)
