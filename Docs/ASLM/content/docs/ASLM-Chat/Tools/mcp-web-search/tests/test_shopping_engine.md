---
title: "test_shopping_engine"
draft: false
---

## Module `test_shopping_engine`

`Tools/mcp-web-search/tests/test_shopping_engine.py` — ASLM Chat Python module.

---

## Overview

Unit tests for the shopping search engine components, including routing and regional limits.

---

## Classes

*None*

---

## Public functions

#### `@pytest.mark.unit def test_shopping_engine_medium_effort_mixes_primary_secondary_60_40(monkeypatch) -> None`

**Purpose:** Implements `test_shopping_engine_medium_effort_mixes_primary_secondary_60_40` in `test_shopping_engine.py`.

#### `@pytest.mark.unit def test_shopping_engine_hot_swaps_secondary_after_failures(monkeypatch) -> None`

**Purpose:** Implements `test_shopping_engine_hot_swaps_secondary_after_failures` in `test_shopping_engine.py`.

#### `@pytest.mark.unit def test_shopping_engine_backfills_primary_shortfall_from_secondary(monkeypatch) -> None`

**Purpose:** Implements `test_shopping_engine_backfills_primary_shortfall_from_secondary` in `test_shopping_engine.py`.

#### `@pytest.mark.unit def test_shopping_engine_runs_primary_and_secondary_concurrently(monkeypatch) -> None`

**Purpose:** Implements `test_shopping_engine_runs_primary_and_secondary_concurrently` in `test_shopping_engine.py`.

#### `@pytest.mark.unit def test_shopping_engine_returns_partial_buffer_on_hard_timeout(monkeypatch) -> None`

**Purpose:** Implements `test_shopping_engine_returns_partial_buffer_on_hard_timeout` in `test_shopping_engine.py`.

#### `@pytest.mark.unit def test_shopping_engine_partial_primary_buffer_is_not_cut_to_primary_quota(monkeypatch) -> None`

**Purpose:** Implements `test_shopping_engine_partial_primary_buffer_is_not_cut_to_primary_quota` in `test_shopping_engine.py`.

#### `@pytest.mark.unit def test_shopping_engine_skips_provider_already_in_cooldown(monkeypatch) -> None`

**Purpose:** Implements `test_shopping_engine_skips_provider_already_in_cooldown` in `test_shopping_engine.py`.

#### `@pytest.mark.unit def test_shopping_provider_router_prefers_russian_sources_for_ru() -> None`

**Purpose:** Implements `test_shopping_provider_router_prefers_russian_sources_for_ru` in `test_shopping_engine.py`.

#### `@pytest.mark.unit def test_shopping_provider_router_prefers_chinese_aggregator_for_zh() -> None`

**Purpose:** Implements `test_shopping_provider_router_prefers_chinese_aggregator_for_zh` in `test_shopping_engine.py`.

#### `@pytest.mark.unit def test_shopping_provider_router_prefers_japanese_aggregator_for_ja() -> None`

**Purpose:** Implements `test_shopping_provider_router_prefers_japanese_aggregator_for_ja` in `test_shopping_engine.py`.

#### `@pytest.mark.unit def test_shopping_engine_passes_language_to_routes(monkeypatch) -> None`

**Purpose:** Implements `test_shopping_engine_passes_language_to_routes` in `test_shopping_engine.py`.

#### `@pytest.mark.unit def test_shopping_engine_waits_for_regional_primary_before_secondary_early_return(monkeypatch) -> None`

**Purpose:** Implements `test_shopping_engine_waits_for_regional_primary_before_secondary_early_return` in `test_shopping_engine.py`.

#### `@pytest.mark.unit def test_shopping_engine_uses_longer_hard_timeout_for_regional_routes() -> None`

**Purpose:** Implements `test_shopping_engine_uses_longer_hard_timeout_for_regional_routes` in `test_shopping_engine.py`.

#### `@pytest.mark.unit def test_shopping_engine_sets_favicon_proxy_without_fetching_favicon(monkeypatch) -> None`

**Purpose:** Implements `test_shopping_engine_sets_favicon_proxy_without_fetching_favicon` in `test_shopping_engine.py`.

#### `@pytest.mark.unit def test_shopping_providers_use_probe_selected_single_transport() -> None`

**Purpose:** Implements `test_shopping_providers_use_probe_selected_single_transport` in `test_shopping_engine.py`.

#### `@pytest.mark.unit def test_shopping_result_json_includes_timings(monkeypatch) -> None`

**Purpose:** Implements `test_shopping_result_json_includes_timings` in `test_shopping_engine.py`.

#### `def asyncio_run(coro)`

**Purpose:** Implements `asyncio_run` in `test_shopping_engine.py`.

---

## Private functions

#### `def _html(provider: str, count: int, *, currency: str='$') -> str`

**Purpose:** Implements `_html` in `test_shopping_engine.py`.

---

## Related

- [tests](../_index/)
