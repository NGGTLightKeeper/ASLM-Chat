---
title: "google_genai"
draft: false
---

## Module `google_genai`

`API/google_genai.py` — see source for implementation details.

---

## Classes

### `class _ReasoningTextParser`

**Purpose:** Data or behavior type `_ReasoningTextParser` in `google_genai.py`.

---

## Public functions

#### `def abort_generation() -> None`

**Purpose:** Signal the active Google GenAI generation to stop.

**Steps:**

1. Execute the implementation in the source module.

#### `def _ReasoningTextParser.__init__(tag_pairs) -> None`

**Purpose:** Initialize the parser state.

**Steps:**

1. Iterate over items and accumulate or transform state.

#### `def _ReasoningTextParser.feed(content, reasoning_type) -> tuple[str, str]`

**Purpose:** Return parsed ``(thinking, visible_content)`` fragments.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _ReasoningTextParser.flush() -> tuple[str, str]`

**Purpose:** Flush any pending partial fragment at the end of the stream.

**Steps:**

1. Return the computed result to the caller.

#### `def get_models() -> list[Any]`

**Purpose:** Return models exposed by the configured Gemini API endpoint.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def download_model(model_name, **kwargs) -> Any`

**Purpose:** Raise because Gemini API models are remote and cannot be downloaded locally.

**Steps:**

1. Raise on invalid input or failure conditions.

#### `def get_model_settings(model_name) -> dict[str, Any]`

**Purpose:** Return capability metadata for one model from Google GenAI.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def generate(model_name, messages, **kwargs)`

**Purpose:** Generate a streamed or non-streamed response through Google GenAI.

**Steps:**

1. Iterate over items and accumulate or transform state.

---

## Private functions

#### `def _clone_cache_payload(value) -> dict[str, Any]`

**Purpose:** Return a safe shallow copy for one cached payload.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _get_sdk()`

**Purpose:** Import the Google GenAI SDK lazily so the app can boot without it.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate over items and accumulate or transform state.

#### `def _normalize_google_base_url(base_url) -> tuple[str, str | None]`

**Purpose:** Split a configured Gemini endpoint into ``(base_url, api_version)``.

**Steps:**

1. Return the computed result to the caller.

#### `def _get_runtime_scope() -> str`

**Purpose:** Return the normalized endpoint scope used for Gemini runtime caches.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _get_api_key_hash() -> str`

**Purpose:** Return a stable non-reversible hash for the active Gemini API key.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _get_model_capability_cache_key(model_name) -> tuple[str, str]`

**Purpose:** Return the stable capability-cache key for one Gemini model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _get_model_availability_cache_key(model_name) -> tuple[str, str, str]`

**Purpose:** Return the stable key-scoped availability-cache key for one Gemini model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _get_cached_model_capabilities(model_name) -> dict[str, Any]`

**Purpose:** Return cached endpoint-scoped capabilities for one Gemini model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _update_cached_model_capabilities(model_name, **updates) -> dict[str, Any]`

**Purpose:** Merge new endpoint-scoped capability facts into the runtime cache.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _get_cached_model_availability(model_name) -> dict[str, Any] | None`

**Purpose:** Return key-scoped availability info when the cache entry is still fresh.

**Steps:**

1. Return the computed result to the caller.

#### `def _set_cached_model_availability(model_name, available, reason) -> dict[str, Any]`

**Purpose:** Cache whether one Gemini model is usable for the current key and endpoint.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _reset_runtime_caches() -> None`

**Purpose:** Clear Gemini runtime caches. Intended for tests and debug flows.

**Steps:**

1. Iterate over items and accumulate or transform state.

#### `def _close_client(client) -> None`

**Purpose:** Safely close a client instance when the SDK exposes ``close``.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def _get_client()`

**Purpose:** Create a fresh Google GenAI client for the configured Gemini API endpoint.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _normalize_key_name(value) -> str`

**Purpose:** Return a normalized lower-case identifier for one key or token.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _bool_from_value(value, default) -> bool`

**Purpose:** Return a predictable boolean from JSON-like payloads.

**Steps:**

1. Return the computed result to the caller.

#### `def _coerce_positive_int(value) -> int | None`

**Purpose:** Convert a scalar into a positive integer when possible.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _coerce_string_list(value) -> list[str]`

**Purpose:** Convert a scalar or collection into a normalized list of strings.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _encode_binary_payload(value) -> str | None`

**Purpose:** Return one binary payload as a base64 string for JSON-safe storage.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _decode_binary_payload(value) -> bytes | None`

**Purpose:** Decode one stored base64 payload back into raw bytes.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _sanitize_generated_text(text) -> str`

**Purpose:** Drop service control tokens that should never reach the chat UI.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _to_plain_data(value) -> Any`

**Purpose:** Convert SDK objects into plain Python containers.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate over items and accumulate or transform state.

#### `def _normalize_model_identifier(value) -> str`

**Purpose:** Return a normalized model identifier for fuzzy Gemini comparisons.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _model_identifiers_match(expected, actual) -> bool`

**Purpose:** Return whether two Gemini model identifiers likely refer to the same model.

**Steps:**

1. Return the computed result to the caller.

#### `def _extract_model_name(payload) -> str`

**Purpose:** Return the UI-facing model identifier for one Gemini model payload.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _iter_model_payloads(client) -> list[dict[str, Any]]`

**Purpose:** Return base and tuned Gemini model payloads when available.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate over items and accumulate or transform state.

#### `def _get_model_payload(client, model_name) -> dict[str, Any]`

**Purpose:** Return capability metadata for one Gemini model.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate over items and accumulate or transform state.

#### `def _tokenize_string(value) -> set[str]`

**Purpose:** Split one free-form value into normalized capability tokens.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _collect_capability_tokens(value) -> set[str]`

**Purpose:** Return normalized tokens extracted from a nested model payload.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _extract_feature_flag(value, feature_names) -> bool | None`

**Purpose:** Return one nested boolean-ish feature flag when it exists.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _extract_supported_actions(raw_model) -> set[str]`

**Purpose:** Return normalized Gemini supported action names.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _get_google_error_payload(exc) -> dict[str, Any]`

**Purpose:** Return the structured Google SDK error payload when present.

**Steps:**

1. Return the computed result to the caller.

#### `def _get_google_error_entries(exc) -> list[dict[str, Any]]`

**Purpose:** Return structured per-error detail entries from one Google SDK error.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _get_google_error_code(exc) -> int | None`

**Purpose:** Return the structured Google SDK error code when available.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _get_google_error_status(exc) -> str`

**Purpose:** Return the structured Google SDK status marker when available.

**Steps:**

1. Return the computed result to the caller.

#### `def _get_google_error_message(exc) -> str`

**Purpose:** Return the structured Google SDK message when available.

**Steps:**

1. Return the computed result to the caller.

#### `def _iter_quota_violations(exc) -> list[dict[str, Any]]`

**Purpose:** Return flattened quota violations from one structured Google SDK error.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _error_mentions_model(exc, model_name) -> bool`

**Purpose:** Return whether the structured error likely refers to the provided model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _is_resource_exhausted_error(exc) -> bool`

**Purpose:** Return whether the error represents one Google quota/rate-limit failure.

**Steps:**

1. Return the computed result to the caller.

#### `def _is_zero_quota_error(exc, model_name) -> bool`

**Purpose:** Return whether the error indicates zero entitlement for the current key/model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _is_generate_content_unsupported_error(exc, model_name) -> bool`

**Purpose:** Return whether the backend says the model cannot serve ``generateContent``.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _is_tool_unsupported_error(exc) -> bool`

**Purpose:** Return whether one backend error explicitly says tools are unsupported.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _is_thinking_level_unsupported_error(exc) -> bool`

**Purpose:** Return whether the backend explicitly rejected Gemini ``thinking_level``.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _learn_from_google_error(model_name, exc) -> str | None`

**Purpose:** Update runtime caches from one structured Google SDK error.

**Steps:**

1. Return the computed result to the caller.

#### `def _coerce_reasoning_level_options(value) -> list[str]`

**Purpose:** Return normalized reasoning level options from one nested metadata value.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _extract_reasoning_level_options(value) -> list[str]`

**Purpose:** Search nested Gemini metadata for explicit reasoning-level options.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _build_model_capability_snapshot(client, model_name, raw_model, *, allow_tool_probe=…, allow_think_level_probe=…) -> dict[str, Any]`

**Purpose:** Return endpoint-scoped Gemini capabilities for one model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _probe_tool_calling_support(client, model_name) -> bool | None`

**Purpose:** Best-effort runtime validation that a Gemini model accepts function tools.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate over items and accumulate or transform state.

#### `def _probe_thinking_level_support(client, model_name) -> bool | None`

**Purpose:** Best-effort runtime validation that a Gemini model accepts ``thinking_level``.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _probe_model_availability(client, model_name) -> bool`

**Purpose:** Return whether one Gemini chat model should stay visible for the current key.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate over items and accumulate or transform state.

#### `def _normalize_tool_call_arguments(raw_arguments) -> dict[str, Any]`

**Purpose:** Return one tool-call arguments payload as a dictionary.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _decode_image_bytes(image_base64) -> bytes`

**Purpose:** Decode one base64-encoded image attachment.

**Steps:**

1. Return the computed result to the caller.

#### `def _normalize_tool_response_payload(content) -> dict[str, Any]`

**Purpose:** Convert tool result content into Gemini function response JSON.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _normalize_google_request_parts(raw_parts) -> list[dict[str, Any]]`

**Purpose:** Normalize OpenAI-style or Gemini-style content parts into Gemini request parts.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _build_google_history_part(raw_part, *, include_text=…) -> dict[str, Any] | None`

**Purpose:** Serialize one assistant response part for transcript replay.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _history_parts_have_function_call(parts) -> bool`

**Purpose:** Return whether preserved Gemini history already includes function calls.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _google_parts_have_unsigned_function_call(raw_parts) -> bool`

**Purpose:** Return whether preserved Gemini parts contain a function call without its signature.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _build_google_contents(messages) -> tuple[str, list[dict[str, Any]]]`

**Purpose:** Convert ASLM chat messages into Gemini-compatible contents.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _build_google_tools(tool_server_ids, model_name) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]`

**Purpose:** Return Gemini-compatible tool declarations for one or more servers.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _coerce_stop_sequences(value) -> list[str] | None`

**Purpose:** Convert a stop payload into the Gemini list form.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _build_google_request_config(options, *, system_instruction=…, think=…, think_level=…, think_param_name=…, think_level_param_name=…, tools=…) -> dict[str, Any]`

**Purpose:** Split generic generation options into a Gemini ``GenerateContentConfig`` payload.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _config_uses_thinking_level(config) -> bool`

**Purpose:** Return whether one Gemini request config currently sends ``thinking_level``.

**Steps:**

1. Return the computed result to the caller.

#### `def _strip_thinking_level_from_config(config) -> dict[str, Any]`

**Purpose:** Return a cloned Gemini request config without ``thinking_level``.

**Steps:**

1. Return the computed result to the caller.

#### `def _apply_learned_request_preferences(model_name, config) -> dict[str, Any]`

**Purpose:** Apply learned runtime capability overrides to one Gemini request config.

**Steps:**

1. Return the computed result to the caller.

#### `def _strip_tools_from_config(config) -> dict[str, Any]`

**Purpose:** Return a request config clone with function tools disabled.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_tool_event(tool_lookup, tool_call) -> dict[str, Any]`

**Purpose:** Serialize one tool invocation so the UI can render it during streaming.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_tool_message(tool_name, tool_call_id, content, tool_event) -> dict[str, Any]`

**Purpose:** Build a tool message payload for the shared ASLM transcript.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _ReasoningTextParser._find_next_tag(source, tags) -> tuple[int, str] | None`

**Purpose:** Implement `_ReasoningTextParser._find_next_tag` as defined in `google_genai.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _ReasoningTextParser._split_possible_tag_prefix(source, tags) -> tuple[str, str]`

**Purpose:** Implement `_ReasoningTextParser._split_possible_tag_prefix` as defined in `google_genai.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _get_response_parts(response) -> list[Any]`

**Purpose:** Return the first-candidate response parts from one SDK response object.

**Steps:**

1. Return the computed result to the caller.

#### `def _parse_google_response_parts(parser, parts) -> tuple[str, str, list[dict[str, Any]]]`

**Purpose:** Parse visible text, reasoning text, and tool calls from one SDK response.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _stream_google_round(client, model_name, contents, config, *, stream=…)`

**Purpose:** Stream one Gemini round and return the assembled assistant message.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate over items and accumulate or transform state.
4. Parse or serialize JSON payloads.

#### `def _yield_stream_round(round_stream)`

**Purpose:** Yield every chunk from a round stream and return the final assistant message.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate over items and accumulate or transform state.

#### `def _assistant_message_to_content(assistant_message) -> dict[str, Any] | None`

**Purpose:** Convert one assembled assistant message back into Gemini conversation content.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _run_tool_loop(client, model_name, messages, options, tool_server_ids, tool_context, *, think=…, think_level=…, think_param_name=…, think_level_param_name=…, stream=…)`

**Purpose:** Resolve local tools through Gemini function-calling while keeping ASLM transcript markers.

**Steps:**

1. Iterate over items and accumulate or transform state.

#### `def _conversation_uses_tools(messages) -> bool`

**Purpose:** Return whether the current conversation already contains tool state.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

---

## Related

- [API/_index](_index/)
