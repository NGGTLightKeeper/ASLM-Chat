---
title: "lms"
draft: false
---

## Module `lms`

`API/lms.py` — ASLM Chat Python module.

---

## Overview

Part of `API`. See **Related** for package index and callers.

---

## Classes

### `class _ReasoningTextParser`

**Purpose:** Type `_ReasoningTextParser` defined in `lms.py`.

---

## Public functions

#### `def abort_generation() -> None`

**Purpose:** Signal the active LM Studio generation to stop.

#### `def _ReasoningTextParser.__init__(tag_pairs) -> None`

**Purpose:** Initialize parser state.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _ReasoningTextParser.feed(content, reasoning_type) -> tuple[str, str]`

**Purpose:** Return parsed ``(thinking, visible_content)`` fragments.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _ReasoningTextParser.flush() -> tuple[str, str]`

**Purpose:** Flush any pending partial fragment at the end of the stream.

**Steps:**

1. Return the computed result to the caller.

#### `def get_models() -> list[Any]`

**Purpose:** Return models available in the configured LM Studio server.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def cleanup_runtime() -> None`

**Purpose:** LM Studio model lifecycle is managed outside this adapter.

#### `def download_model(model_name, **kwargs) -> Any`

**Purpose:** Raise because LM Studio downloads are managed outside this adapter.

#### `def generate(model_name, messages, **kwargs)`

**Purpose:** Generate a streamed or non-streamed response through LM Studio.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def get_model_settings(model_name) -> dict[str, Any]`

**Purpose:** Return capability metadata for one already-loaded LM Studio model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _ensure_model_loaded(client, model_name) -> None`

**Purpose:** Get-or-load the requested model so generation can run on downloaded models.

#### `def _extract_api_host(raw_address) -> str`

**Purpose:** Normalize the configured LM Studio address into a client host value.

**Steps:**

1. Return the computed result to the caller.

#### `def _get_sdk()`

**Purpose:** Import the LM Studio SDK lazily so the app can boot without it.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def _get_client()`

**Purpose:** Create a fresh LM Studio client for the configured server.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _close_client(client) -> None`

**Purpose:** Safely close a client instance when the SDK exposes ``close``.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def _get_model_handle(client, model_name)`

**Purpose:** Return an SDK handle for one already-loaded model.

#### `def _coerce_model_name(entry) -> str`

**Purpose:** Extract a stable model identifier from LM Studio SDK objects.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _collect_unique_model_names(entries) -> list[str]`

**Purpose:** Return unique model names while preserving the original order.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _list_models_with_client(method_name) -> list[Any]`

**Purpose:** Call one LM Studio listing method and always close the client.

**Steps:**

1. Return the computed result to the caller.

#### `def _bool_from_value(value, default) -> bool`

**Purpose:** Return a predictable boolean from SDK and dict payloads.

**Steps:**

1. Return the computed result to the caller.

#### `def _config_signature(config) -> str`

**Purpose:** Return a stable hashable signature for one LM Studio config.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _normalize_model_identifier(value) -> str`

**Purpose:** Return a normalized model identifier for fuzzy LM Studio comparisons.

#### `def _model_identifiers_match(expected, actual) -> bool`

**Purpose:** Return whether two LM Studio model identifiers likely refer to the same model.

**Steps:**

1. Return the computed result to the caller.

#### `def _list_loaded_model_names(client) -> list[str]`

**Purpose:** Return loaded model names visible to the current LM Studio client.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _assert_model_is_loaded(client, model_name) -> None`

**Purpose:** Raise when the requested model is not already loaded in LM Studio.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Iterate and transform or accumulate state.

#### `def _serialize_model_info(info) -> dict[str, Any]`

**Purpose:** Convert SDK model info into a JSON-compatible dictionary.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _get_raw_model_info(client, model_name) -> dict[str, Any]`

**Purpose:** Return the raw LM Studio model-info payload when the SDK exposes it.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _clean_nested_config(value) -> Any`

**Purpose:** Drop empty nested config values while preserving scalars.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _normalize_model_config(config) -> dict[str, Any]`

**Purpose:** Return a normalized dictionary for raw LM Studio config sections.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _merge_nested_dicts(base, override) -> dict[str, Any]`

**Purpose:** Recursively merge two dictionaries without mutating either input.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _get_lmstudio_home() -> str`

**Purpose:** Return the local LM Studio home directory.

**Steps:**

1. Return the computed result to the caller.

#### `def _read_json_file(path) -> Any`

**Purpose:** Return decoded JSON from one file path when it exists.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _unwrap_kv_field_value(value) -> Any`

**Purpose:** Convert LM Studio checkbox-like KV values into plain Python values.

**Steps:**

1. Return the computed result to the caller.

#### `def _set_nested_client_value(target, path, value) -> None`

**Purpose:** Assign one normalized value into a nested client-config dictionary.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _apply_kv_mapping(target, mapping, parts, value) -> bool`

**Purpose:** Apply one LM Studio KV field through the SDK mapping when possible.

**Steps:**

1. Return the computed result to the caller.

#### `def _kv_field_fallback_path(prefix, remainder) -> str`

**Purpose:** Return a best-effort client path for one unmapped LM Studio KV field.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _kv_fields_to_client_config(section_key, fields) -> dict[str, Any]`

**Purpose:** Convert LM Studio KV field lists into the adapter's client-config shape.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _get_model_index_record(model_name) -> dict[str, Any]`

**Purpose:** Return the local LM Studio model-index record for one model identifier.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _get_disk_model_operation_defaults(model_name) -> dict[str, Any]`

**Purpose:** Return saved LM Studio operation defaults for one model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _get_model_default_config_path(model_name) -> str`

**Purpose:** Return the LM Studio user default-config path for one model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _sync_operation_defaults_to_disk(model_name, operation_config) -> None`

**Purpose:** Persist custom LM Studio operation fields so the server applies them during generation.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _extract_reasoning_settings(operation_defaults) -> tuple[Any | None, Any | None]`

**Purpose:** Return canonical reasoning toggle and level defaults from operation config.

**Steps:**

1. Return the computed result to the caller.

#### `def _collect_reasoning_field_hints(field_definition) -> str`

**Purpose:** Build one searchable string for reasoning custom-field detection.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _detect_reasoning_custom_fields(raw_info) -> tuple[str | None, Any | None, str | None, Any | None]`

**Purpose:** Infer reasoning toggle/level custom fields from LM Studio model metadata.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_reasoning_level_options(raw_info) -> list[str]`

**Purpose:** Return supported reasoning level values from LM Studio custom fields.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _get_local_gpu_devices() -> list[dict[str, Any]]`

**Purpose:** Return local NVIDIA GPU devices with both numeric ids and labels.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Spawn or communicate with a child process.

#### `def _sanitize_generated_text(text) -> str`

**Purpose:** Drop service control tokens that should never reach the chat UI.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _get_model_info(client, model_name) -> tuple[Any | None, dict[str, Any]]`

**Purpose:** Return model info from the SDK or loaded-model listing.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _build_reasoning_parsing_config(enabled) -> dict[str, Any]`

**Purpose:** Return the default reasoning parsing config for LM Studio.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _append_raw_kv_field(target, key, value) -> None`

**Purpose:** Append one raw LM Studio KV field to a request config.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _prepare_native_prediction_options(options, think, think_level, think_param_name, think_level_param_name) -> dict[str, Any]`

**Purpose:** Normalize LM Studio SDK prediction options.

**Steps:**

1. Return the computed result to the caller.

#### `def _prepare_openai_prediction_options(options, think, think_level, think_param_name, think_level_param_name) -> dict[str, Any]`

**Purpose:** Normalize LM Studio OpenAI-compatible options for tool-calling flows.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _get_openai_client()`

**Purpose:** Create an OpenAI client pointing at the LM Studio server.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def _build_openai_messages(messages) -> list[dict[str, Any]]`

**Purpose:** Convert ASLM chat messages into OpenAI-compatible payloads.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_tool_event(tool_lookup, tool_call) -> dict[str, Any]`

**Purpose:** Serialize one tool invocation so the UI can render it during streaming.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_tool_message(tool_name, tool_call_id, content, tool_event) -> dict[str, Any]`

**Purpose:** Build a tool message payload for the OpenAI-compatible conversation.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _ReasoningTextParser._find_next_tag(source, tags) -> tuple[int, str] | None`

**Purpose:** Implements `_ReasoningTextParser._find_next_tag` in `lms.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _ReasoningTextParser._split_possible_tag_prefix(source, tags) -> tuple[str, str]`

**Purpose:** Implements `_ReasoningTextParser._split_possible_tag_prefix` in `lms.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _prepare_image_handle(client, image_base64, name, cache) -> Any`

**Purpose:** Upload one image to LM Studio and return its file handle.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_native_chat_history(client, messages)`

**Purpose:** Convert generic chat messages into an LM Studio chat history.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _stream_native_response(model, chat, options, stream)`

**Purpose:** Yield parsed LM Studio SDK output.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _stream_openai_round(client, model_name, conversation, options, tools)`

**Purpose:** Stream one LM Studio round via OpenAI API and return the assembled message.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _yield_stream_round(round_stream)`

**Purpose:** Yield every chunk from a round stream and return the final assistant message.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _run_tool_loop(client, model_name, messages, options, tool_server_ids, tool_context, *, conversation=…)`

**Purpose:** Resolve local tools through LM Studio's OpenAI-compatible tool-calling.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.
3. Parse or serialize JSON payloads.

#### `def _conversation_uses_tools(messages) -> bool`

**Purpose:** Return whether the current conversation already contains tool state.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [API/_index](../_index/)
