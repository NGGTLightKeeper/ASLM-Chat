---
title: "mcp"
draft: false
---

## Module `mcp`

`API/mcp.py` — MCP tool discovery, schema export, and execution for chat adapters.

---

## Overview

Discovers bundled `Tools/*/mcp-server.py` and user MCP servers, builds Ollama/OpenAI tool schemas, and executes tool calls in-process or via `Services/tool_worker` subprocesses. Enforces per-turn quotas, cooldowns, and optional search I/O logging.


---

## Classes

### `class AsyncCallableRunner`

**Purpose:** Type `AsyncCallableRunner` defined in `mcp.py`.

### `class ExternalWorkerSession`

**Purpose:** Type `ExternalWorkerSession` defined in `mcp.py`.

---

## Public functions

#### `def AsyncCallableRunner.__init__() -> None`

**Purpose:** Initialize the shared runner state.

#### `def AsyncCallableRunner.ensure_started() -> None`

**Purpose:** Start the background loop thread when it is not already running.

#### `def AsyncCallableRunner.run(coro, *, timeout=…) -> Any`

**Purpose:** Run one coroutine on the shared loop and wait for its result.

**Steps:**

1. Return the computed result to the caller.

#### `def AsyncCallableRunner.close() -> None`

**Purpose:** Stop the background loop and join its thread.

#### `def ExternalWorkerSession.__init__(server_file, python_path) -> None`

**Purpose:** Bind one worker process to a server entrypoint and venv Python.

**Steps:**

1. Spawn or communicate with a child process.

#### `def ExternalWorkerSession.request(operation, payload, *, timeout_s=…) -> Any`

**Purpose:** Send one request to the worker process and return its result.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.
5. Parse or serialize JSON payloads.

#### `def ExternalWorkerSession.close() -> None`

**Purpose:** Stop the worker process if it is running.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.
3. Spawn or communicate with a child process.

#### `def log_search_tool_io(phase, tool_event, arguments, context, result, error, elapsed_seconds) -> None`

**Purpose:** Log exactly what search/read-page tools receive from and return to the model.

**Steps:**

1. Return the computed result to the caller.

#### `def consume_tool_quota(tool_event, counters, arguments) -> str | None`

**Purpose:** Increment one quota counter and return an error message if the call is over limit.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def is_blocking_tool_result(result) -> bool`

**Purpose:** Return whether a tool result is a guardrail/block message, not fresh evidence.

**Steps:**

1. Return the computed result to the caller.

#### `def forced_final_prompt_after_tool_blocks() -> str`

**Purpose:** Return the instruction used when the tool loop must stop retrying tools.

#### `def consume_duplicate_tool_call(tool_event, arguments, seen_signatures) -> str | None`

**Purpose:** Return an error message when the same quota-controlled tool call repeats.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def consume_tool_cooldown(tool_event, arguments) -> str | None`

**Purpose:** Block repeated search/read-page calls within a short cooldown window.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def remember_tool_cooldown(tool_event, arguments) -> None`

**Purpose:** Mark search/read-page calls as recently used.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def consume_read_page_cooldown(tool_event, arguments) -> str | None`

**Purpose:** Delegate read_page cooldown checks to the shared tool cooldown helper.

#### `def remember_read_page_cooldown(tool_event, arguments) -> None`

**Purpose:** Delegate read_page cooldown bookkeeping to the shared tool cooldown helper.

#### `def reset_cache() -> None`

**Purpose:** Clear cached discovery so local edits are picked up immediately.

#### `def close_external_workers() -> None`

**Purpose:** Stop persistent external tool workers owned by this process.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def list_servers(engine, model_name) -> list[dict[str, Any]]`

**Purpose:** Return discovered servers that support the current engine and model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def get_server(server_id, engine, model_name) -> dict[str, Any] | None`

**Purpose:** Return one discovered server when it is available in the current context.

**Steps:**

1. Return the computed result to the caller.

#### `def build_ollama_tools(server_ids, engine, model_name) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]`

**Purpose:** Return Ollama-compatible tool payloads for one or more selected servers.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def split_tool_result_payload(content) -> tuple[str, dict[str, Any]]`

**Purpose:** Split one tool result into model-visible text and UI-only metadata.

**Steps:**

1. Return the computed result to the caller.

#### `def call_ollama_tool(tool_lookup, alias, arguments, context) -> str | dict`

**Purpose:** Execute a local tool and serialize its result for Ollama.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

---

## Private functions

#### `def AsyncCallableRunner._thread_main() -> None`

**Purpose:** Host the dedicated asyncio loop on a background thread.

#### `def _get_async_callable_runner() -> AsyncCallableRunner`

**Purpose:** Return the process-wide async callable runner singleton.

**Steps:**

1. Return the computed result to the caller.

#### `def _venv_subprocess_env(python_path) -> dict[str, str]`

**Purpose:** Return subprocess environment aligned with the selected venv.

**Steps:**

1. Return the computed result to the caller.
2. Spawn or communicate with a child process.

#### `def ExternalWorkerSession._start() -> None`

**Purpose:** Spawn the worker process when it is missing or has exited.

**Steps:**

1. Spawn or communicate with a child process.

#### `def ExternalWorkerSession._read_response_line(timeout_s) -> str`

**Purpose:** Read worker protocol lines until a final envelope arrives.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.
5. Parse or serialize JSON payloads.

#### `def _print_runtime_event(message) -> None`

**Purpose:** Emit one console-visible runtime event.

#### `def _worker_timeout_seconds(operation, payload) -> float`

**Purpose:** Return a wall-clock timeout for one worker request.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _is_debug_logging_enabled() -> bool`

**Purpose:** Return whether debug-or-higher MCP events should be printed.

#### `def _is_trace_logging_enabled() -> bool`

**Purpose:** Return whether trace-level MCP events should be printed.

#### `def _preview_jsonish(value, limit) -> str`

**Purpose:** Return a compact one-line preview for arguments and results.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _summarize_tool_result(result) -> str`

**Purpose:** Return a short textual summary of a tool result payload.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _summarize_tool_context(context) -> str`

**Purpose:** Return a compact summary of the runtime context passed into a tool.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _quota_tool_id(tool_event) -> str`

**Purpose:** Return the canonical tool id used for per-response quotas.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _search_effort(arguments) -> str`

**Purpose:** Return the normalized web-search effort value from tool arguments.

**Steps:**

1. Return the computed result to the caller.

#### `def _tool_quota_limit(quota_tool_id, arguments) -> int`

**Purpose:** Return the per-response quota for one tool call.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _write_search_io_event(event) -> None`

**Purpose:** Append complete model/search tool IO as a readable JSON array.

**Steps:**

1. Handle errors and map them to a safe response.
2. Parse or serialize JSON payloads.

#### `def _without_duplicate_preview(value) -> Any`

**Purpose:** Remove preview fields from diagnostics when they exactly duplicate snippet.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _canonical_tool_arguments(value) -> Any`

**Purpose:** Return a stable representation for duplicate tool-call detection.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _read_page_urls(arguments) -> list[str]`

**Purpose:** Extract normalized read_page URL arguments from one tool payload.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _normalize_read_page_url(url) -> str`

**Purpose:** Normalize one read_page URL for cooldown comparison.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _normalize_cooldown_value(value) -> Any`

**Purpose:** Normalize one cooldown key payload for stable comparison.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _tool_cooldown_keys(tool_event, arguments) -> list[tuple[str, str]]`

**Purpose:** Build cooldown keys for one search or read_page tool invocation.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _tool_cooldown_message(tool_id, entries) -> str`

**Purpose:** Format the duplicate-tool cooldown message shown to the model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _iter_server_source_files(server_dir)`

**Purpose:** Yield relevant source files for one local MCP server.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _server_signature() -> tuple[tuple[str, int], ...]`

**Purpose:** Build a stable signature for every local MCP server source file.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _iter_server_files()`

**Purpose:** Yield top-level MCP server entrypoints from the Tools directory.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _slugify(value) -> str`

**Purpose:** Normalize folder and public identifiers into a stable slug.

**Steps:**

1. Return the computed result to the caller.

#### `def _purge_modules_under(server_root) -> None`

**Purpose:** Drop previously imported modules loaded from one tool directory.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def _load_module(server_file) -> ModuleType`

**Purpose:** Load one ``mcp-server.py`` file into an isolated Python module.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def _get_worker_python(server_file) -> Path | None`

**Purpose:** Return the isolated Python executable assigned to one tool server.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _get_worker_session(server_file) -> ExternalWorkerSession`

**Purpose:** Return a long-lived worker session for one external tool server.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def _run_worker(server_file, operation, payload, *, persistent=…) -> Any`

**Purpose:** Run a tool worker operation and return its result payload.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.
5. Parse or serialize JSON payloads.
6. Spawn or communicate with a child process.

#### `def _load_external_server(server_file) -> dict[str, Any]`

**Purpose:** Load one server definition without importing it into the Django process.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def _normalize_schema(schema) -> dict[str, Any]`

**Purpose:** Return a JSON-schema-like mapping suitable for tool payloads.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _resolve_server_callable(module)`

**Purpose:** Return the generic server dispatcher when one is exported.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _normalize_tool_handlers(module) -> dict[str, Any]`

**Purpose:** Return explicit per-tool handlers exported by a server module.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _normalize_server_tools(raw_tools, server_id) -> list[dict[str, Any]]`

**Purpose:** Validate and normalize tool definitions exposed by one server.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def _merge_user_mcp_servers(discovered) -> None`

**Purpose:** Append servers from ``MCP/mcp.json`` to the registry payload.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def _extract_server_definition(module, folder_name, server_file) -> dict[str, Any]`

**Purpose:** Validate a local MCP module and normalize its public metadata.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def _ensure_registry_loaded() -> dict[str, dict[str, Any]]`

**Purpose:** Discover and cache valid local MCP-style server modules.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _server_is_supported(server_definition, engine, model_name) -> bool`

**Purpose:** Return whether a server supports the current engine and model.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _serialize_tool(tool_definition) -> dict[str, Any]`

**Purpose:** Return the frontend-facing representation of one tool.

**Steps:**

1. Return the computed result to the caller.

#### `def _serialize_server(server_definition) -> dict[str, Any]`

**Purpose:** Return the frontend-facing representation of one server.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `async def _run_async_callable(callable_fn, *args) -> Any`

**Purpose:** Execute an async callable with the provided arguments.

#### `def _run_sync_callable(callable_fn, *args) -> Any`

**Purpose:** Execute a synchronous callable with the provided arguments.

#### `def _execute_callable(callable_fn, *args) -> Any`

**Purpose:** Execute sync and async callables behind one shared helper.

**Steps:**

1. Return the computed result to the caller.

#### `def _dispatch_server_callable(callable_fn, tool_id, arguments, context) -> Any`

**Purpose:** Call a generic server dispatcher with a tolerant signature strategy.

**Steps:**

1. Return the computed result to the caller.

#### `def _serialize_tool_result(result) -> str`

**Purpose:** Convert a tool result into text suitable for a model tool message.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.
3. Parse or serialize JSON payloads.

#### `def _coerce_tool_result_object(result) -> Any`

**Purpose:** Parse JSON tool payloads returned as plain strings.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _extract_shared_file_payload(result) -> dict[str, Any] | None`

**Purpose:** Return a normalized shared-file payload from direct or sandbox-wrapped results.

**Steps:**

1. Return the computed result to the caller.

#### `def _extract_structured_tool_result(result) -> dict[str, Any] | None`

**Purpose:** Return frontend metadata for rich structured tool results.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _image_tool_result_extras(content) -> dict[str, Any]`

**Purpose:** Build UI-only metadata for an inline image tool result.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_inline_image_payload(result) -> dict[str, Any] | None`

**Purpose:** Extract an Ollama image payload from the sandbox v2 read envelope.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [API/_index](../_index/)
