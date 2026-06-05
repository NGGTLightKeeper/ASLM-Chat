---
title: "history_compressor"
draft: false
---

## Module `history_compressor`

`Tools/context_compression/history_compressor.py` — see source for implementation details.

---

## Classes

### `class CompressionDecision`

**Purpose:** Data or behavior type `CompressionDecision` in `history_compressor.py`.

---

## Public functions

#### `def resolve_context_window_tokens(model_info_payload, *, runtime_metadata_path=…, active_engine=…, active_model=…) -> int`

**Purpose:** Resolve context window size from model info, then from runtime metadata when available.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate over items and accumulate or transform state.
4. Parse or serialize JSON payloads.

#### `def decide_compression(*, used_history_chars, history_budget_chars, model_info_payload, runtime_metadata_path, active_engine, active_model, debug_force_4k=…, trigger_ratio=…) -> CompressionDecision`

**Purpose:** Decide whether history compression should run for the current character budget.

**Steps:**

1. Return the computed result to the caller.

#### `def fit_summary_text(summary_payload, max_chars) -> tuple[str, dict[str, Any]]`

**Purpose:** Fit a summary into a character budget while preserving valid JSON.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate over items and accumulate or transform state.
4. Parse or serialize JSON payloads.

#### `def build_structured_history_summary(*, overflow_entries, recent_user_messages, direct_user_directives, summarize_with_model, max_overflow_entries=…) -> tuple[str, dict[str, Any]]`

**Purpose:** Build the structured history compression block and parsed payload metadata.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.
3. Parse or serialize JSON payloads.

---

## Private functions

#### `def _strip_control_tokens(text) -> str`

**Purpose:** Remove model control tokens and thinking wrappers from transcript text.

**Steps:**

1. Return the computed result to the caller.

#### `def _entry_text(entry, max_chars) -> str`

**Purpose:** Format one history entry as role-prefixed text for generic compression prompts.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _is_noisy_url(url) -> bool`

**Purpose:** Return True when a URL points at localhost, Bing, or other low-value hosts.

**Steps:**

1. Return the computed result to the caller.

#### `def _clean_url(url) -> str`

**Purpose:** Normalize a URL string and drop noisy or empty values.

**Steps:**

1. Return the computed result to the caller.

#### `def _looks_like_web_host_path(value) -> bool`

**Purpose:** Detect host/path strings that should be treated as URLs rather than file paths.

**Steps:**

1. Return the computed result to the caller.

#### `def _file_basename(value) -> str`

**Purpose:** Return the final path segment from a Windows or POSIX path string.

#### `def _file_extension(value) -> str`

**Purpose:** Return the extension after the last dot, matching Path.suffix semantics.

#### `def _extension_body(value) -> str`

**Purpose:** Return the extension body without the leading dot.

#### `def _looks_like_code_fragment(value) -> bool`

**Purpose:** Reject identifier.token shapes produced by the file regex over source code.

**Steps:**

1. Return the computed result to the caller.

#### `def _looks_like_valid_path(value) -> bool`

**Purpose:** Validate a candidate file path extracted from chat text.

**Steps:**

1. Return the computed result to the caller.

#### `def _is_assistant_navigation(text) -> bool`

**Purpose:** Return True when text matches known assistant navigation openers.

#### `def _passes_semantic_threshold(text) -> bool`

**Purpose:** Require minimum length and reject title-case-only heading fragments.

**Steps:**

1. Return the computed result to the caller.

#### `def _clean_memory_text(text) -> str`

**Purpose:** Remove repeated tool boilerplate while preserving useful facts.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _entry_memory_text(entry, max_chars) -> str`

**Purpose:** Build a sanitized role-prefixed memory line for one transcript entry.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _tool_observation_text(entry, max_chars) -> str`

**Purpose:** Return a compact observation from a tool result without raw tool-call logs.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _compression_prompt_entry_text(entry) -> str`

**Purpose:** Choose the best compact text representation for one compression-prompt entry.

**Steps:**

1. Return the computed result to the caller.

#### `def _scoped_context_entries(entries) -> list[dict[str, Any]]`

**Purpose:** Keep the first and last entries around the compressed span for model context.

**Steps:**

1. Return the computed result to the caller.

#### `def _looks_like_raw_tool_dump(text) -> bool`

**Purpose:** Detect text that still looks like an unprocessed tool or search dump.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _sanitize_semantic_items(values, *, limit, max_chars, allow_tool_memory=…, apply_semantic_threshold=…) -> list[str]`

**Purpose:** Normalize, filter, and dedupe semantic list fields on a summary payload.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _sanitize_open_tasks(values, *, limit=…) -> list[str]`

**Purpose:** Sanitize open_tasks with stricter semantic thresholds than generic lists.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _dedupe_strings(values, *, limit=…) -> list[str]`

**Purpose:** Deduplicate strings case-insensitively while preserving first-seen order.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _line_candidates(text) -> list[str]`

**Purpose:** Extract non-trivial lines suitable for fact or observation harvesting.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _empty_summary_payload() -> dict[str, Any]`

**Purpose:** Return the canonical empty structured summary object.

**Steps:**

1. Return the computed result to the caller.

#### `def _raw_context_payload(overflow_entries, recent_user_messages, *, warning=…, raw_model_output=…) -> dict[str, Any]`

**Purpose:** Build a fallback summary payload by scanning overflow entries without a model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _sanitize_summary_payload(model_payload) -> dict[str, Any]`

**Purpose:** Clamp and sanitize every field on a model-produced summary payload.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _merge_model_summary_with_raw_context(model_payload, raw_payload) -> dict[str, Any]`

**Purpose:** Merge model summary fields with deterministic raw-context harvest results.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _summary_text_from_payload(payload) -> str`

**Purpose:** Serialize a summary payload into the stored compression marker text.

#### `def _extract_json_object(text) -> dict[str, Any] | None`

**Purpose:** Parse a JSON object from raw model text, including fenced or prose-wrapped payloads.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _empty_markdown_value(text) -> bool`

**Purpose:** Return True when a Markdown field value is effectively empty.

#### `def _markdown_list_items(lines) -> list[str]`

**Purpose:** Parse bullet list lines from a Markdown section body.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _markdown_block(lines) -> str`

**Purpose:** Join non-empty Markdown section lines into a single block string.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _normalize_markdown_heading(heading) -> str`

**Purpose:** Normalize a Markdown heading or label for canonical section lookup.

**Steps:**

1. Return the computed result to the caller.

#### `def _canonical_markdown_section(heading) -> str`

**Purpose:** Resolve a heading string to an internal summary field name, if recognized.

#### `def _extract_markdown_summary(text) -> dict[str, Any] | None`

**Purpose:** Parse fixed-section Markdown model output into a summary payload dict.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _extract_summary_payload(text) -> dict[str, Any] | None`

**Purpose:** Parse model output as JSON first, then as contract Markdown sections.

---

## Related

- [context_compression/_index](_index/)
