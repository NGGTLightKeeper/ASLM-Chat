---
title: "test_search_core"
draft: false
---

## Module `test_search_core`

`Tools/mcp-web-search/tests/test_search_core.py` — ASLM Chat Python module.

---

## Overview

Offline coverage for the new search core: quality, triage, health, orchestrator.

---

## Classes

### `class _Clock`

**Purpose:** Type `_Clock` defined in `test_search_core.py`.

#### `def _Clock.__init__()`

**Purpose:** Implements `_Clock.__init__` in `test_search_core.py`.

### `class _FakeSerpApi`

Replays a scripted event stream.

#### `def _FakeSerpApi.__init__()`

**Purpose:** Implements `_FakeSerpApi.__init__` in `test_search_core.py`.

#### `def _FakeSerpApi.search_stream()`

**Purpose:** Implements `_FakeSerpApi.search_stream` in `test_search_core.py`.

### `class _Profiles`

**Purpose:** Type `_Profiles` defined in `test_search_core.py`.

#### `def _Profiles.__init__(ms)`

**Purpose:** Implements `_Profiles.__init__` in `test_search_core.py`.

#### `def _Profiles.best_method(_domain)`

**Purpose:** Implements `_Profiles.best_method` in `test_search_core.py`.

---

## Public functions

#### `def test_lexical_word_boundary_no_substring_false_positive()`

**Purpose:** Implements `test_lexical_word_boundary_no_substring_false_positive` in `test_search_core.py`.

#### `def test_hub_penalty_flags_category_pages()`

**Purpose:** Implements `test_hub_penalty_flags_category_pages` in `test_search_core.py`.

#### `def test_skip_title_patterns()`

**Purpose:** Implements `test_skip_title_patterns` in `test_search_core.py`.

#### `def test_year_policy_soft_only()`

**Purpose:** Implements `test_year_policy_soft_only` in `test_search_core.py`.

#### `def test_infer_query_language_scripts()`

**Purpose:** Implements `test_infer_query_language_scripts` in `test_search_core.py`.

#### `def test_triage_relevant_top_google_parses_immediately()`

**Purpose:** Implements `test_triage_relevant_top_google_parses_immediately` in `test_search_core.py`.

#### `def test_triage_skip_title_is_skipped()`

**Purpose:** Implements `test_triage_skip_title_is_skipped` in `test_search_core.py`.

#### `def test_triage_consensus_upgrades_queued_source()`

**Purpose:** Implements `test_triage_consensus_upgrades_queued_source` in `test_search_core.py`.

#### `def test_triage_google_startpage_one_family_vote()`

**Purpose:** Implements `test_triage_google_startpage_one_family_vote` in `test_search_core.py`.

#### `def test_breaker_error_opens_for_five_minutes()`

**Purpose:** Implements `test_breaker_error_opens_for_five_minutes` in `test_search_core.py`.

#### `def test_breaker_degradation_short_cooldown_and_recovery()`

**Purpose:** Implements `test_breaker_degradation_short_cooldown_and_recovery` in `test_search_core.py`.

#### `def test_breaker_failed_probe_backs_off_exponentially()`

**Purpose:** Implements `test_breaker_failed_probe_backs_off_exponentially` in `test_search_core.py`.

#### `def test_breaker_abandoned_probe_is_expired_not_wedged()`

**Purpose:** Implements `test_breaker_abandoned_probe_is_expired_not_wedged` in `test_search_core.py`.

#### `def test_select_engines_low_default_pair()`

**Purpose:** Implements `test_select_engines_low_default_pair` in `test_search_core.py`.

#### `def test_select_engines_low_falls_back_to_startpage()`

**Purpose:** Implements `test_select_engines_low_falls_back_to_startpage` in `test_search_core.py`.

#### `def test_select_engines_low_never_empty()`

**Purpose:** Implements `test_select_engines_low_never_empty` in `test_search_core.py`.

#### `def test_select_engines_medium_startpage_standby_when_google_open()`

**Purpose:** Implements `test_select_engines_medium_startpage_standby_when_google_open` in `test_search_core.py`.

#### `def test_custom_domain_scope_marks_browser_heavy_readpage_only()`

**Purpose:** Implements `test_custom_domain_scope_marks_browser_heavy_readpage_only` in `test_search_core.py`.

#### `def test_inline_parse_blocks_readpage_only_handler()`

**Purpose:** Implements `test_inline_parse_blocks_readpage_only_handler` in `test_search_core.py`.

#### `def test_inline_parse_skips_learned_slow_domain(monkeypatch)`

**Purpose:** Implements `test_inline_parse_skips_learned_slow_domain` in `test_search_core.py`.

#### `def test_inline_parse_allows_unknown_domain()`

**Purpose:** Implements `test_inline_parse_allows_unknown_domain` in `test_search_core.py`.

#### `def test_web_search_medium_parses_winners_and_ranks(monkeypatch)`

**Purpose:** Implements `test_web_search_medium_parses_winners_and_ranks` in `test_search_core.py`.

#### `def test_web_search_hosted_consensus_merges_not_overwrites(monkeypatch)`

**Purpose:** Implements `test_web_search_hosted_consensus_merges_not_overwrites` in `test_search_core.py`.

#### `def test_web_search_low_is_serp_only(monkeypatch)`

**Purpose:** Implements `test_web_search_low_is_serp_only` in `test_search_core.py`.

---

## Private functions

#### `def _ingest(session)`

**Purpose:** Implements `_ingest` in `test_search_core.py`.

#### `def _fake_reader(url) -> str`

**Purpose:** Implements `_fake_reader` in `test_search_core.py`.

---

## Related

- [core](../../_index/)
