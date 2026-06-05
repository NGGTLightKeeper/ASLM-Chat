---
title: "ollama"
draft: false
---

## Module `ollama`

`API/ollama.py` — see source for implementation details.

---

## Public functions

#### `def abort_generation() -> None`

**Purpose:** Signal the active Ollama generation to stop.

**Steps:**

1. Execute the implementation in the source module.

#### `def prepare_runtime(engine) -> None`

**Purpose:** Ensure the managed Ollama runtime is running before requests.

**Steps:**

1. Execute the implementation in the source module.

#### `def cleanup_runtime() -> None`

**Purpose:** Stop the managed Ollama runtime when the engine is deselected.

**Steps:**

1. Execute the implementation in the source module.

#### `def is_supported_runtime_option_key(option_name) -> bool`

**Purpose:** Return whether the option can be forwarded to the current Ollama chat API.

**Steps:**

1. Return the computed result to the caller.

#### `def get_client() -> ollama.Client`

**Purpose:** Create an Ollama client using the configured local service port.

**Steps:**

1. Return the computed result to the caller.

#### `def get_models() -> list[dict[str, Any]]`

**Purpose:** Return the locally available Ollama models.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def download_model(model_name, **kwargs) -> Any`

**Purpose:** Pull a model from Ollama.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def get_model_settings(model_name) -> Any`

**Purpose:** Return metadata and Modelfile-style settings for an Ollama model.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate over items and accumulate or transform state.

#### `def generate(model_name, messages, **kwargs) -> Any`

**Purpose:** Generate a chat response through Ollama.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate over items and accumulate or transform state.

---

## Private functions

#### `def _get_ollama_service_module()`

**Purpose:** Import the managed Ollama service module lazily.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _print_runtime_event(message) -> None`

**Purpose:** Emit one ASLM-Chat runtime event into the shared console.

**Steps:**

1. Execute the implementation in the source module.

#### `def _is_debug_logging_enabled() -> bool`

**Purpose:** Return whether debug-or-higher Ollama adapter events should be printed.

**Steps:**

1. Return the computed result to the caller.

#### `def _is_trace_logging_enabled() -> bool`

**Purpose:** Return whether trace-level adapter events should be printed.

**Steps:**

1. Return the computed result to the caller.

#### `def _preview_jsonish(value, limit) -> str`

**Purpose:** Return a compact one-line preview for adapter diagnostics.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate over items and accumulate or transform state.
4. Parse or serialize JSON payloads.

#### `def _summarize_tool_names(tool_calls) -> str`

**Purpose:** Return a readable summary of tool aliases requested by the model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _call_with_runtime_retry(operation, description) -> Any`

**Purpose:** Run an Ollama operation after giving the managed runtime time to answer.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate over items and accumulate or transform state.

#### `def _get_field(value, *names, default=…) -> Any`

**Purpose:** Return the first matching field from dict-like or attribute objects.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _normalize_tool_call(raw_call) -> dict[str, Any] | None`

**Purpose:** Convert an Ollama tool-call payload into a predictable dictionary.

**Steps:**

1. Return the computed result to the caller.

#### `def _merge_tool_calls(existing, incoming) -> list[dict[str, Any]]`

**Purpose:** Merge streamed tool-call chunks without duplicating entries.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _normalize_message(raw_message) -> dict[str, Any]`

**Purpose:** Convert an Ollama message object into a JSON-compatible dictionary.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _sanitize_request_options(options) -> tuple[Any, list[str]]`

**Purpose:** Drop Ollama options that the bundled runtime no longer accepts.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _report_dropped_options(dropped_options) -> None`

**Purpose:** Log one concise summary when unsupported Ollama options are removed.

**Steps:**

1. Iterate over items and accumulate or transform state.

#### `def _prepare_chat_kwargs_with_metadata(kwargs) -> tuple[dict[str, Any], list[str]]`

**Purpose:** Move supported top-level Ollama parameters out of nested options.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _prepare_chat_kwargs(kwargs) -> dict[str, Any]`

**Purpose:** Compatibility wrapper that returns only the Ollama call kwargs.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_tool_message(tool_name, content, tool_event) -> dict[str, Any]`

**Purpose:** Build a tool message payload that can be fed back into Ollama.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_tool_event(tool_lookup, tool_call) -> dict[str, Any]`

**Purpose:** Serialize one tool invocation so the UI can render it during streaming.

**Steps:**

1. Return the computed result to the caller.

#### `def _stream_round(client, model_name, conversation, base_kwargs, tools)`

**Purpose:** Stream one Ollama round and return the assembled assistant message.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _yield_stream_round(round_stream)`

**Purpose:** Yield every chunk from a round stream and return the final assistant message.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate over items and accumulate or transform state.

#### `def _run_tool_loop(client, model_name, messages, call_kwargs, tool_server_ids, tool_context)`

**Purpose:** Resolve local tools through Ollama tool-calling with streaming output.

**Steps:**

1. Iterate over items and accumulate or transform state.

#### `def _iter_with_abort(iterator)`

**Purpose:** Yield iterator chunks until a cancellation request arrives.

**Steps:**

1. Iterate over items and accumulate or transform state.

---

## Related

- [API/_index](_index/)
