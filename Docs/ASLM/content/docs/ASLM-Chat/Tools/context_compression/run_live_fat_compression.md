---
title: "run_live_fat_compression"
draft: false
---

## Module `run_live_fat_compression`

`Tools/context_compression/run_live_fat_compression.py` — ASLM Chat Python module.

---

## Public functions

#### `def main() -> None`

**Purpose:** Run raw-only and model-backed compression against the bundled fat chat and write a report.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Iterate and transform or accumulate state.
3. Parse or serialize JSON payloads.

---

## Private functions

#### `def _configure_runtime() -> tuple[str, int]`

**Purpose:** Point Settings at the compression engine port before importing API modules.

**Steps:**

1. Return the computed result to the caller.

#### `def _count_noise(values) -> int`

**Purpose:** Count list values that still contain raw tool dumps or noisy URLs.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _bad_files(files) -> list[str]`

**Purpose:** Flag artifact file paths that fail validation or look like code fragments.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _bad_source_memory(items) -> list[str]`

**Purpose:** Flag source_memory lines that are assistant navigation filler.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _pick_model(engine) -> str`

**Purpose:** Choose a local model name from the active engine, preferring smaller local tags.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def _chunk_visible_text(chunk) -> str`

**Purpose:** Extract visible assistant text from a streamed or dict-shaped LLM chunk.

**Steps:**

1. Return the computed result to the caller.

#### `def _summarize_with_model(engine, model_name)`

**Purpose:** Build a non-streaming summarize callback for the compression prompt.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def _report(label, payload) -> dict[str, int | list[str]]`

**Purpose:** Summarize sanitization metrics for one compression payload.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [context_compression/_index](../../_index/)
