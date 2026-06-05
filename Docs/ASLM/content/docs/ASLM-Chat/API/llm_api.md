---
title: "llm_api"
draft: false
---

## Module `llm_api`

`API/llm_api.py` — ASLM Chat Python module.

---

## Overview

Facade over engine adapters (`ollama`, `lms`, `openai`, `google_genai`). Resolves the active engine from `Settings`, calls `prepare_runtime`, and delegates `get_models`, `generate`, and `abort_generation`.


---

## Public functions

#### `def get_models(engine) -> Any`

**Purpose:** Return the list of models exposed by the selected engine.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def download_model(engine, model_name, **kwargs) -> Any`

**Purpose:** Download or pull a model through the selected engine adapter.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def generate(engine, model_name, messages, **kwargs) -> Any`

**Purpose:** Generate a chat response through the selected engine adapter.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def abort_generation(engine) -> None`

**Purpose:** Signal the active generation for one engine or every loaded adapter.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def get_model_settings(engine, model_name) -> Any`

**Purpose:** Return model metadata exposed by the selected engine.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def reload_model(engine, model_name) -> None`

**Purpose:** Reload the selected model when the engine supports explicit reloads.

**Steps:**

1. Raise on invalid input or failure conditions.

#### `def prepare_runtime(engine) -> None`

**Purpose:** Prepare the selected engine runtime before it is used.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def cleanup_runtime(engine) -> None`

**Purpose:** Release runtime resources for the selected engine.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def handle_engine_transition(previous_engine, next_engine) -> None`

**Purpose:** Switch runtime resources when the active engine changes.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _get_engine_module(engine) -> ModuleType`

**Purpose:** Load the adapter module for the selected LLM engine.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

---

## Related

- [API/_index](../_index/)
