---
title: "test_search_core"
draft: false
---

## Module `test_search_core`

`Tools/mcp-web-search/tests/test_search_core.py` — ASLM Chat Python module.

---

## Test methods

#### `def test_lexical_word_boundary_no_substring_false_positive() -> None`

**Purpose:** test_lexical_word_boundary_no_substring_false_positive

#### `def test_hub_penalty_flags_category_pages() -> None`

**Purpose:** test_hub_penalty_flags_category_pages

#### `def test_skip_title_patterns() -> None`

**Purpose:** test_skip_title_patterns

#### `def test_year_policy_soft_only() -> None`

**Purpose:** test_year_policy_soft_only

#### `def test_infer_query_language_scripts() -> None`

**Purpose:** test_infer_query_language_scripts

#### `def test_triage_relevant_top_google_parses_immediately() -> None`

**Purpose:** test_triage_relevant_top_google_parses_immediately

#### `def test_triage_skip_title_is_skipped() -> None`

**Purpose:** test_triage_skip_title_is_skipped

#### `def test_triage_consensus_upgrades_queued_source() -> None`

**Purpose:** test_triage_consensus_upgrades_queued_source

#### `def test_triage_google_startpage_one_family_vote() -> None`

**Purpose:** test_triage_google_startpage_one_family_vote

#### `def test_breaker_error_opens_for_five_minutes() -> None`

**Purpose:** test_breaker_error_opens_for_five_minutes

#### `def test_breaker_degradation_short_cooldown_and_recovery() -> None`

**Purpose:** test_breaker_degradation_short_cooldown_and_recovery

#### `def test_breaker_failed_probe_backs_off_exponentially() -> None`

**Purpose:** test_breaker_failed_probe_backs_off_exponentially

#### `def test_breaker_abandoned_probe_is_expired_not_wedged() -> None`

**Purpose:** A half-open probe whose outcome is never recorded (e.g. the search deadline dropped the engine's status event) must not lock the engine out forever.

#### `def test_select_engines_low_default_pair() -> None`

**Purpose:** test_select_engines_low_default_pair

#### `def test_select_engines_low_falls_back_to_startpage() -> None`

**Purpose:** test_select_engines_low_falls_back_to_startpage

#### `def test_select_engines_low_never_empty() -> None`

**Purpose:** test_select_engines_low_never_empty

#### `def test_select_engines_medium_startpage_standby_when_google_open() -> None`

**Purpose:** test_select_engines_medium_startpage_standby_when_google_open

#### `def test_web_search_medium_parses_winners_and_ranks(monkeypatch) -> None`

**Purpose:** test_web_search_medium_parses_winners_and_ranks

#### `def test_web_search_low_is_serp_only(monkeypatch) -> None`

**Purpose:** test_web_search_low_is_serp_only

---

## Related

- [tests/_index](../_index/)
