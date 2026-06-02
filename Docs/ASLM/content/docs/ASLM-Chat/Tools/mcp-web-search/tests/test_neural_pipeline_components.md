---
title: "test_neural_pipeline_components"
draft: false
---

## Module `test_neural_pipeline_components`

`Tools/mcp-web-search/tests/test_neural_pipeline_components.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\tests`. See **Related** for package index and callers.

---

## Test methods

#### `def test_model_paths_resolve_under_models_dir() -> None`

**Purpose:** Implements `test_model_paths_resolve_under_models_dir` in `test_neural_pipeline_components.py`.

#### `def test_aslm_model_exports_exist_on_disk() -> None`

**Purpose:** Implements `test_aslm_model_exports_exist_on_disk` in `test_neural_pipeline_components.py`.

#### `def test_search_model_session_can_be_disabled_and_closed() -> None`

**Purpose:** test_search_model_session_can_be_disabled_and_closed — load=False leaves encoder/decoder None.

#### `def test_search_model_session_respects_component_flags(monkeypatch) -> None`

**Purpose:** test_search_model_session_respects_component_flags — env disables decoder while encoder loads.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_model_device_resolver_is_explicit_cuda_opt_in(monkeypatch) -> None`

**Purpose:** test_model_device_resolver_is_explicit_cuda_opt_in — _resolve_device honors cpu/cuda/auto.

#### `def test_single_class_mix_adds_general_fallback() -> None`

**Purpose:** test_single_class_mix_adds_general_fallback — single-class mix gets general backfill.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_source_budget_allocation_sums_to_total() -> None`

**Purpose:** test_source_budget_allocation_sums_to_total — allocate_source_budget partitions max_results.

#### `def test_routing_score_uses_registry_weights() -> None`

**Purpose:** test_routing_score_uses_registry_weights — pubmed URL gets json_api and multiplier > 1.

#### `def test_source_cache_records_class_metadata(tmp_path) -> None`

**Purpose:** test_source_cache_records_class_metadata — query_source_classes row stores mix and scores.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def test_pipeline_mode_aliases() -> None`

**Purpose:** test_pipeline_mode_aliases — legacy/neural_v2 aliases normalize to rules/aslm_embedding.

#### `def test_pipeline_rules_disables_neural_stack(monkeypatch) -> None`

**Purpose:** test_pipeline_rules_disables_neural_stack — pipeline env and encoder flag gate _use_neural_pipeline.

#### `def test_keep_models_loaded_env_defaults_to_disabled(monkeypatch) -> None`

**Purpose:** test_keep_models_loaded_env_defaults_to_disabled — ASLM_WEB_SEARCH_KEEP_MODELS parsing.

#### `def test_search_model_device_env_overrides_config(monkeypatch) -> None`

**Purpose:** test_search_model_device_env_overrides_config — ASLM_WEB_SEARCH_MODEL_DEVICE env wins.

#### `def test_search_model_session_scope_clears_shared_when_neural_off(monkeypatch) -> None`

**Purpose:** test_search_model_session_scope_clears_shared_when_neural_off — medium effort with keep_models=0 skips load.

**Steps:**

1. Return the computed result to the caller.

#### `def test_shared_model_session_reuses_loaded_session(monkeypatch) -> None`

**Purpose:** test_shared_model_session_reuses_loaded_session — same FakeSession instance on second get.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [tests/_index](../../../_index/)
