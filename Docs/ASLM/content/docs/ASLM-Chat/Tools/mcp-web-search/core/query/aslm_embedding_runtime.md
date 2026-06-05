---
title: "aslm_embedding_runtime"
draft: false
---

## Module `aslm_embedding_runtime`

`Tools/mcp-web-search/core/query/aslm_embedding_runtime.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\query`. See **Related** for package index and callers.

---

## Classes

### `class AslmEmbeddingPrediction`

**Purpose:** Type `AslmEmbeddingPrediction` defined in `aslm_embedding_runtime.py`.

### `class AslmEmbeddingRuntime`

**Purpose:** Type `AslmEmbeddingRuntime` defined in `aslm_embedding_runtime.py`.

### `class SearchModelSession`

**Purpose:** Type `SearchModelSession` defined in `aslm_embedding_runtime.py`.

---

## Public functions

#### `def AslmEmbeddingPrediction.top(limit) -> list[tuple[str, float]]`

**Purpose:** Top label probabilities sorted descending.

#### `def AslmEmbeddingRuntime.__init__(export_dir, *, device=…, max_length=…) -> None`

**Purpose:** Load tokenizer, encoder, and heads from an on-disk export directory.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def AslmEmbeddingRuntime.predict(texts) -> list[AslmEmbeddingPrediction]`

**Purpose:** Batch inference: sigmoid label probs and scalar relevance per text.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def AslmEmbeddingRuntime.close() -> None`

**Purpose:** Drop model refs and clear CPU/CUDA caches.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def load_aslm_embedding_export(export_dir, *, device=…) -> AslmEmbeddingRuntime`

**Purpose:** Implements `load_aslm_embedding_export` in `aslm_embedding_runtime.py`.

#### `def SearchModelSession.__init__(*, load=…, device=…, load_encoder=…, load_decoder=…) -> None`

**Purpose:** Configure which models to load and resolve device from env flags.

#### `def SearchModelSession.__enter__() -> 'SearchModelSession'`

**Purpose:** Load encoder and/or decoder when session enters context.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def SearchModelSession.__exit__(exc_type, exc, tb) -> None`

**Purpose:** Release models when session exits context.

#### `def SearchModelSession.ready() -> bool`

**Purpose:** Implements `SearchModelSession.ready` in `aslm_embedding_runtime.py`.

#### `def SearchModelSession.close() -> None`

**Purpose:** Close loaded encoder and decoder runtimes.

#### `def SearchModelSession.classify_query(query) -> AslmEmbeddingPrediction | None`

**Purpose:** Run encoder query classifier; None if encoder not loaded.

#### `def SearchModelSession.score_snippet_candidates(query, candidates) -> list[AslmEmbeddingPrediction]`

**Purpose:** Score SERP snippet candidates with decoder (no page preview).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def SearchModelSession.score_parsed_candidates(query, candidates) -> list[AslmEmbeddingPrediction]`

**Purpose:** Score fetched page candidates with decoder including preview text.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def default_query_classifier_path(root) -> Path`

**Purpose:** Default on-disk path for query classifier (encoder) export.

#### `def default_source_relevance_path(root) -> Path`

**Purpose:** Default on-disk path for source relevance (decoder) export.

#### `def format_source_relevance_input(*, query, title, url, snippet=…, preview=…) -> str`

**Purpose:** Fixed template for decoder relevance scoring input.

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `def _env_component_enabled(name, *, default=…) -> bool`

**Purpose:** Read boolean env flag (0/false/no/off/disabled → False).

**Steps:**

1. Return the computed result to the caller.

#### `def _resolve_device(device) -> str`

**Purpose:** Map device string (auto, cuda, gpu) to torch device name.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

---

## Related

- [query/_index](../../../../_index/)
