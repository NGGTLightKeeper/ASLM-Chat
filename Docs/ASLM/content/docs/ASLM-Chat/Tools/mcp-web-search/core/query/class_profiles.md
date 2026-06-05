---
title: "class_profiles"
draft: false
---

## Module `class_profiles`

`Tools/mcp-web-search/core/query/class_profiles.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\query`. See **Related** for package index and callers.

---

## Classes

### `class ClassProfile`

**Purpose:** Type `ClassProfile` defined in `class_profiles.py`.

### `class ClassRuleScore`

**Purpose:** Type `ClassRuleScore` defined in `class_profiles.py`.

---

## Public functions

#### `def load_class_profiles() -> dict[str, ClassProfile]`

**Purpose:** Implements `load_class_profiles` in `class_profiles.py`.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def clear_class_profiles_cache() -> None`

**Purpose:** Clear cached class profiles for tests or hot reload.

#### `def score_query_against_profiles(query) -> list[ClassRuleScore]`

**Purpose:** Score query against all loaded profiles; scores normalized to 0..1.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def infer_query_types_from_rules(query, limit) -> list[str]`

**Purpose:** Rule-only classification compatible with legacy infer_query_types() ordering.

#### `def infer_query_types_hybrid(query, model_scores) -> list[tuple[str, float, str]]`

**Purpose:** Hybrid router: model_scores primary, rules adjust; returns (class, weight, reason).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def journalistic_intent_terms() -> frozenset[str]`

**Purpose:** Terms for freshness/intent detection (from journalistic profile).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _profile_from_dict(data) -> ClassProfile`

**Purpose:** Build ClassProfile from one JSON profile object.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def _validate_profile_file(path, data) -> None`

**Purpose:** Validate one profile JSON file before merge into cache.

#### `def _normalize_text(text) -> str`

**Purpose:** Lowercase and collapse non-alphanumeric runs to spaces.

#### `def _char_trigrams(text) -> set[str]`

**Purpose:** Character trigram set for fuzzy term matching.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _trigram_similarity(a, b) -> float`

**Purpose:** Jaccard similarity of character trigram sets.

**Steps:**

1. Return the computed result to the caller.

#### `def _term_in_query(term, query_norm, tokens, query_raw_lower) -> bool`

**Purpose:** True when term matches query via token, phrase, or boundary regex.

**Steps:**

1. Return the computed result to the caller.

#### `def _fuzzy_term_match(term, query_norm) -> tuple[bool, float]`

**Purpose:** Trigram fuzzy match for a single term against normalized query.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _collect_language_terms(profile) -> list[str]`

**Purpose:** Flatten all language_hints term lists for one profile.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _rule_scores_map(query) -> dict[str, float]`

**Purpose:** Map class name to rule score for one query.

#### `def _top_rule_classes(scores, limit, min_score) -> list[str]`

**Purpose:** Pick top non-general classes by score and CLASS_PRIORITY order.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _normalize_model_scores(model_scores) -> dict[str, float]`

**Purpose:** Normalize model label scores to a probability distribution.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [query/_index](../../../../_index/)
