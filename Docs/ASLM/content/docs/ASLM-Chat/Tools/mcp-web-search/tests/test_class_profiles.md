---
title: "test_class_profiles"
draft: false
---

## Module `test_class_profiles`

`Tools/mcp-web-search/tests/test_class_profiles.py` — ASLM Chat Python module.

---

## Test methods

#### `def test_load_all_class_profiles() -> None`

**Purpose:** load_class_profiles — all 21 priority classes load with descriptions.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_trigram_catches_close_variants() -> None`

**Purpose:** _trigram_similarity — fuzzy match close spellings.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_obvious_technical_scores_high() -> None`

**Purpose:** score_query_against_profiles — obvious technical queries score high.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_technical_special_terms_do_not_match_unrelated_substrings(query) -> None`

**Purpose:** Implements `test_technical_special_terms_do_not_match_unrelated_substrings` in `test_class_profiles.py`.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_technical_symbol_terms_match_explicit_forms(query) -> None`

**Purpose:** Implements `test_technical_symbol_terms_match_explicit_forms` in `test_class_profiles.py`.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_obvious_weather_scores_high() -> None`

**Purpose:** score_query_against_profiles — weather queries dominate technical.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_model_split_technical_academic_keeps_both() -> None`

**Purpose:** infer_query_types_hybrid — model split keeps both technical and academic.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_rule_only_order_prefers_score_before_class_priority() -> None`

**Purpose:** infer_query_types_from_rules — score order before CLASS_PRIORITY tie-break.

#### `def test_model_only_technical_adds_general_secondary() -> None`

**Purpose:** infer_query_types_hybrid — model-only technical adds general secondary.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_hard_rule_override_only_at_high_confidence() -> None`

**Purpose:** infer_query_types_hybrid — hard rule override only at high model confidence.

#### `def test_infer_query_types_wrapper_compatible() -> None`

**Purpose:** infer_query_types — public wrapper returns capped finance-first list.

---

## Private functions

#### `def _fresh_profiles() -> None`

**Purpose:** Implements `_fresh_profiles` in `test_class_profiles.py`.

---

## Related

- [tests/_index](../../../_index/)
