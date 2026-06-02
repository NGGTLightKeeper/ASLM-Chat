---
title: "openai"
draft: false
---

## Module `openai`

`API/openai.py` — ASLM Chat Python module.

---

## Overview

Part of `API`. See **Related** for package index and callers.

---

## Classes

### `class _ReasoningTextParser`

**Purpose:** Type `_ReasoningTextParser` defined in `openai.py`.

---

## Public functions

#### `def abort_generation() -> None`

**Purpose:** Signal the active OpenAI-compatible generation to stop.

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

**Purpose:** Return models exposed by the configured OpenAI-compatible endpoint.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def download_model(model_name, **kwargs) -> Any`

**Purpose:** Raise because OpenAI-compatible endpoints expose remote models only.

#### `def get_model_settings(model_name) -> dict[str, Any]`

**Purpose:** Return capability metadata for one model from an OpenAI-compatible endpoint.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def generate(model_name, messages, **kwargs)`

**Purpose:** Generate a streamed or non-streamed response through an OpenAI-compatible API.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _close_client(client) -> None`

**Purpose:** Safely close a client instance when the SDK exposes ``close``.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def _normalize_key_name(value) -> str`

**Purpose:** Return a normalized lower-case identifier for one key or token.

#### `def _bool_from_value(value, default) -> bool`

**Purpose:** Return a predictable boolean from JSON-like payloads.

**Steps:**

1. Return the computed result to the caller.

#### `def _coerce_positive_int(value) -> int | None`

**Purpose:** Convert a scalar into a positive integer when possible.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _merge_nested_dicts(base, override) -> dict[str, Any]`

**Purpose:** Recursively merge two dictionaries without mutating either input.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _clean_nested_config(value) -> Any`

**Purpose:** Drop empty nested config values while preserving scalar defaults.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _to_plain_data(value) -> Any`

**Purpose:** Convert SDK objects into plain Python containers.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _normalize_model_identifier(value) -> str`

**Purpose:** Return a normalized model identifier for fuzzy comparisons.

#### `def _model_identifiers_match(expected, actual) -> bool`

**Purpose:** Return whether two model identifiers likely refer to the same model.

**Steps:**

1. Return the computed result to the caller.

#### `def _iter_values_for_keys(source, target_keys)`

**Purpose:** Yield every nested value whose normalized key matches one target key.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _extract_named_values(value) -> set[str]`

**Purpose:** Extract normalized names from capability-like metadata payloads.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_capability_tokens(raw_model) -> set[str]`

**Purpose:** Return normalized feature tokens exposed by one model payload.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_feature_flag(raw_model, feature_names) -> bool | None`

**Purpose:** Return an explicit boolean capability flag when the payload exposes one.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_defaults_from_container(container) -> dict[str, Any]`

**Purpose:** Extract parameter defaults from one OpenAI-compatible config container.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_option_values(definition) -> list[str]`

**Purpose:** Extract enumerated option values from one parameter definition.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_reasoning_metadata(raw_model) -> tuple[Any | None, Any | None, list[str]]`

**Purpose:** Return reasoning toggle default, level default, and supported levels.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_defaults(raw_model) -> dict[str, Any]`

**Purpose:** Return normalized default runtime options exposed by one model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_parameter_names_from_container(container) -> set[str]`

**Purpose:** Extract parameter identifiers from one OpenAI-compatible schema container.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_supported_parameter_names(raw_model, defaults) -> set[str]`

**Purpose:** Return normalized runtime parameter names exposed by one model payload.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_parameter_option_values(raw_model, parameter_names) -> list[str]`

**Purpose:** Extract one parameter's supported option values from nested model metadata.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _resolve_parameter_name(parameter_names, candidate_names, default_name) -> str`

**Purpose:** Resolve one provider parameter name using exact and suffix matching.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_context_length(raw_model) -> int`

**Purpose:** Return the best context-length value visible in the model metadata.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _endpoint_host_matches(hostname, expected_host) -> bool`

**Purpose:** Return whether one hostname is the expected host or its subdomain.

**Steps:**

1. Return the computed result to the caller.

#### `def _uses_object_reasoning_controls(base_url) -> bool`

**Purpose:** Return whether the configured endpoint expects object-shaped reasoning controls.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _coerce_reasoning_control_object(value, effort) -> dict[str, Any]`

**Purpose:** Convert scalar reasoning controls into the object shape used by some providers.

**Steps:**

1. Return the computed result to the caller.

#### `def _normalize_reasoning_request_options(direct_options, extra_body, *, base_url=…) -> None`

**Purpose:** Normalize reasoning controls in-place for the configured compatible endpoint.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _iter_companion_metadata_roots() -> list[str]`

**Purpose:** Return candidate companion API roots derived from the configured base URL.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _fetch_json_url(url) -> dict[str, Any] | None`

**Purpose:** Return parsed JSON from one URL when it resolves successfully.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _extract_model_catalog_items(payload) -> list[dict[str, Any]]`

**Purpose:** Normalize one companion catalog payload into a list of model records.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _load_companion_model_catalog(url) -> list[dict[str, Any]]`

**Purpose:** Load and cache one companion model catalog endpoint.

**Steps:**

1. Return the computed result to the caller.

#### `def _get_companion_model_payload(model_name) -> dict[str, Any]`

**Purpose:** Return supplemental read-only metadata from companion model catalogs.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _get_model_payload(client, model_name) -> dict[str, Any]`

**Purpose:** Return the richest model metadata available from the remote endpoint.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def _get_client()`

**Purpose:** Create an OpenAI-compatible client using the configured base URL.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def _sanitize_generated_text(text) -> str`

**Purpose:** Drop service control tokens that should never reach the chat UI.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_text_fragment(value, *, reasoning) -> str`

**Purpose:** Extract text or reasoning text from one OpenAI-compatible payload fragment.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_content_text_from_payload(payload) -> str`

**Purpose:** Return visible content text from one choice delta or message payload.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_reasoning_text_from_payload(payload) -> str`

**Purpose:** Return reasoning text from one choice delta or message payload.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_reasoning_type(payload) -> str | None`

**Purpose:** Return the reasoning-fragment type when the backend exposes one.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _normalize_tool_call_arguments(raw_arguments) -> dict[str, Any]`

**Purpose:** Return one tool-call arguments payload as a dictionary.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _merge_tool_call_delta(tool_calls_by_index, raw_tool_call) -> None`

**Purpose:** Merge one streamed tool-call fragment into the accumulated call set.

**Steps:**

1. Handle errors and map them to a safe response.
2. Parse or serialize JSON payloads.

#### `def _build_openai_messages(messages) -> list[dict[str, Any]]`

**Purpose:** Convert ASLM chat messages into OpenAI-compatible payloads.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_openai_request_options(options, **kwargs) -> dict[str, Any]`

**Purpose:** Split generic generation options into direct kwargs and ``extra_body``.

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

**Purpose:** Implements `_ReasoningTextParser._find_next_tag` in `openai.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _ReasoningTextParser._split_possible_tag_prefix(source, tags) -> tuple[str, str]`

**Purpose:** Implements `_ReasoningTextParser._split_possible_tag_prefix` in `openai.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _parse_payload_fragments(parser, payload) -> tuple[str, str]`

**Purpose:** Parse visible and reasoning fragments from one choice payload.

**Steps:**

1. Return the computed result to the caller.

#### `def _stream_openai_round(client, model_name, conversation, options, *, tools=…, stream=…)`

**Purpose:** Stream one OpenAI-compatible round and return the assembled assistant message.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _yield_stream_round(round_stream)`

**Purpose:** Yield every chunk from a round stream and return the final assistant message.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _run_tool_loop(client, model_name, messages, options, tool_server_ids, tool_context, *, stream=…, conversation=…)`

**Purpose:** Resolve local tools through OpenAI-compatible function calling.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _conversation_uses_tools(messages) -> bool`

**Purpose:** Return whether the current conversation already contains tool state.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [API/_index](../_index/)
