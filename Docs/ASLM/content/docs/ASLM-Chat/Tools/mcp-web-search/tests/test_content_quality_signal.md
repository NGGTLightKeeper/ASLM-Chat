---
title: "test_content_quality_signal"
draft: false
---

## Module `test_content_quality_signal`

`Tools/mcp-web-search/tests/test_content_quality_signal.py` — ASLM Chat Python module.

---

## Test methods

#### `def test_bm25_signal_can_exceed_promote_threshold() -> None`

**Purpose:** _content_quality_signal — strong BM25 preview can exceed promote threshold.

#### `def test_bm25_signal_stays_below_promote_for_weak_preview() -> None`

**Purpose:** _content_quality_signal — weak preview stays below promote threshold.

#### `def test_semantic_path_uses_semantic_component() -> None`

**Purpose:** _content_quality_signal — semantic_score component affects the blended signal.

#### `def test_ema_reaches_promote_after_repeated_strong_signals() -> None`

**Purpose:** EMA convergence — repeated strong signals reach PROMOTE_THRESHOLD.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def rep_store(tmp_path) -> DomainReputationStore`

**Purpose:** Implements `rep_store` in `test_content_quality_signal.py`.

#### `def test_auto_promote_after_repeated_bm25_quality_observations(rep_store) -> None`

**Purpose:** DomainReputationStore — repeated strong BM25 observations auto-promote tier C.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_parsed_lexical_beats_serp_only_when_body_matches_query() -> None`

**Purpose:** _parsed_lexical_score — body match beats SERP-only when preview aligns with query.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_parsed_lex_boost_requires_margin_over_serp_lex() -> None`

**Purpose:** _result_score — parsed_lex boost requires margin over SERP lexical score.

#### `def test_resolve_trust_tier_applies_auto_promoted_tier(rep_store) -> None`

**Purpose:** _resolve_result_trust_tier — auto-promoted domain surfaces as trust_tier C.

**Steps:**

1. Iterate and transform or accumulate state.

---

## Private functions

#### `def _result(**kwargs) -> SearchResult`

**Purpose:** Build a default SearchResult for content-quality tests.

**Steps:**

1. Return the computed result to the caller.

#### `def _strong_bm25_observation() -> tuple[PreviewPayload, SearchResult, str, float]`

**Purpose:** Fixture helper: realistic BM25 observation for reputation store tests.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [tests/_index](../../../_index/)
