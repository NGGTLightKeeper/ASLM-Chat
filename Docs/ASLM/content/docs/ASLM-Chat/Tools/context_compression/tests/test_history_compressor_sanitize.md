---
title: "test_history_compressor_sanitize"
draft: false
---

## Module `test_history_compressor_sanitize`

`Tools/context_compression/tests/test_history_compressor_sanitize.py` — ASLM Chat Python module.

---

## Classes

### `class HistoryCompressorSanitizeTests`

**Purpose:** Type `HistoryCompressorSanitizeTests` defined in `test_history_compressor_sanitize.py`.

---

## Test methods

#### `def HistoryCompressorSanitizeTests.test_looks_like_valid_path_rejects_json_escaped_code() -> None`

**Purpose:** _looks_like_valid_path — reject code fragments and accept real file paths.

#### `def HistoryCompressorSanitizeTests.test_sanitize_semantic_items_drops_navigation() -> None`

**Purpose:** _sanitize_semantic_items — drop assistant navigation boilerplate.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def HistoryCompressorSanitizeTests.test_sanitize_semantic_items_drops_bare_headings() -> None`

**Purpose:** _sanitize_semantic_items — drop bare section headings without substance.

#### `def HistoryCompressorSanitizeTests.test_passes_semantic_threshold() -> None`

**Purpose:** _passes_semantic_threshold — headings vs factual lines.

#### `def HistoryCompressorSanitizeTests.test_raw_context_payload_skips_false_windows_paths() -> None`

**Purpose:** _raw_context_payload — extract paths without false positives from escaped newlines.

**Steps:**

1. Iterate and transform or accumulate state.

---

## Related

- [tests/_index](../../../_index/)
