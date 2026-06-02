---
title: "settings"
draft: false
---

## Module `settings`

`Settings/settings.py` — ASLM Chat Python module.

---

## Overview

Part of `Settings`. See **Related** for package index and callers.

---

## Public functions

#### `def normalize_setting_value(value) -> Any`

**Purpose:** Normalize one raw settings value.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def normalize_setting_key(raw_key) -> str`

**Purpose:** Normalize one raw settings key.

**Steps:**

1. Return the computed result to the caller.

#### `def normalize_engine_address(value) -> str`

**Purpose:** Normalize one engine address for storage.

**Steps:**

1. Return the computed result to the caller.

#### `def normalize_engine_name(engine) -> str`

**Purpose:** Normalize one engine identifier.

**Steps:**

1. Return the computed result to the caller.

#### `def get_supported_engines() -> list[dict[str, str]]`

**Purpose:** List engines supported by the UI.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def get_enabled_engine_ids() -> list[str]`

**Purpose:** List enabled engine identifiers from the effective settings.

#### `def resolve_enabled_engine(engine, default) -> str`

**Purpose:** Resolve one requested engine against the current enabled engine list.

#### `def load_settings() -> dict[str, Any]`

**Purpose:** Load the effective settings snapshot.

**Steps:**

1. Return the computed result to the caller.

#### `def save_settings(data) -> None`

**Purpose:** Save the settings snapshot to disk.

#### `def get(key, default) -> Any`

**Purpose:** Read one setting value.

#### `def set(key, value) -> None`

**Purpose:** Persist one setting value.

#### `def get_llm_engine(default) -> str`

**Purpose:** Read the active LLM engine name.

#### `def get_engine_url_key(engine) -> str | None`

**Purpose:** Resolve the settings key for one engine URL.

#### `def get_engine_url(engine) -> str`

**Purpose:** Build the effective engine URL.

**Steps:**

1. Return the computed result to the caller.

#### `def get_openai_api_key() -> str`

**Purpose:** Read the OpenAI-compatible API key.

#### `def get_google_genai_api_key() -> str`

**Purpose:** Read the Google GenAI API key.

**Steps:**

1. Return the computed result to the caller.

#### `def get_engine_api_key_key(engine) -> str | None`

**Purpose:** Resolve the settings key for one engine API key.

#### `def get_engine_api_key(engine) -> str`

**Purpose:** Read the configured API key for one engine.

**Steps:**

1. Return the computed result to the caller.

#### `def get_runtime_engine_settings() -> dict[str, Any]`

**Purpose:** Build the runtime settings payload for the UI.

**Steps:**

1. Return the computed result to the caller.

#### `def get_console_log_level(default) -> str`

**Purpose:** Read the console log level.

#### `def is_console_debug_enabled() -> bool`

**Purpose:** Check whether debug console output is enabled.

#### `def is_console_trace_enabled() -> bool`

**Purpose:** Check whether trace console output is enabled.

#### `def is_engine_enabled(engine) -> bool`

**Purpose:** Check whether one engine is enabled.

#### `def is_ollama_engine(engine) -> bool`

**Purpose:** Check whether the engine uses the Ollama adapter path.

---

## Private functions

#### `def _get_settings_mtime_ns() -> int | None`

**Purpose:** Return the current settings file mtime.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _store_settings_cache(data, mtime_ns) -> None`

**Purpose:** Store one effective settings snapshot in memory.

#### `def _invalidate_settings_cache() -> None`

**Purpose:** Invalidate the in-memory settings snapshot.

#### `def _get_enabled_engine_ids_from_settings(settings_data) -> list[str]`

**Purpose:** List enabled engine identifiers from one settings snapshot.

#### `def _resolve_enabled_engine_from_settings(settings_data, engine, default) -> str`

**Purpose:** Resolve one engine against the enabled engine list.

**Steps:**

1. Return the computed result to the caller.

#### `def _load_settings_from_disk() -> dict[str, Any]`

**Purpose:** Read the settings payload from disk.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _apply_environment_overrides(data) -> dict[str, Any]`

**Purpose:** Apply environment overrides to one settings snapshot.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _warn_port_collisions(settings) -> None`

**Purpose:** Log a warning when two services share the same TCP port.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def _normalize_loaded_settings(data) -> dict[str, Any]`

**Purpose:** Normalize a loaded settings snapshot (addresses, active engine, port checks).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _to_env_var_name(key) -> str`

**Purpose:** Build one runtime environment variable name.

#### `def _serialize_env_value(value) -> str`

**Purpose:** Serialize one value for environment storage.

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

#### `def _apply_process_environment_value(key, value) -> None`

**Purpose:** Apply one runtime setting to the current process environment.

#### `def _load_stored_settings_snapshot() -> dict[str, Any]`

**Purpose:** Load stored settings without applying ASLM_ environment overrides.

#### `def _get_module_manifest_path() -> Path | None`

**Purpose:** Locate the ASLM module manifest when available.

**Steps:**

1. Return the computed result to the caller.

#### `def _sync_module_manifest_setting(key, value) -> None`

**Purpose:** Mirror one runtime setting into the module manifest.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def _infer_remote_scheme(value) -> str`

**Purpose:** Infer a scheme for remote endpoints without one.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [Settings/_index](../_index/)
