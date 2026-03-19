# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import importlib
import logging
from typing import Any

import ollama

from API import mcp as tool_registry
from Settings import settings

logger = logging.getLogger(__name__)

OLLAMA_TOP_LEVEL_CHAT_KEYS = {"format", "keep_alive", "logprobs", "top_logprobs"}
OLLAMA_INTERNAL_CHAT_KEYS = {"system", "prompt", "tool_id", "tool_server_id", "tool_context", "think", "think_level"}
MAX_TOOL_ROUNDS = 100


# Import Ollama service
def _get_ollama_service_module():
    """Import the managed Ollama service module lazily."""

    try:
        return importlib.import_module("Services.ollama-service")
    except ImportError as exc:
        logger.warning("[Ollama API] Could not import Services.ollama-service: %s", exc)
        return None

# Start Ollama runtime
def prepare_runtime() -> None:
    """Ensure the managed Ollama runtime is running before requests."""

    ollama_service = _get_ollama_service_module()
    if ollama_service is not None:
        ollama_service.start_ollama()

# Stop Ollama runtime
def cleanup_runtime() -> None:
    """Stop the managed Ollama runtime when the engine is deselected."""

    ollama_service = _get_ollama_service_module()
    if ollama_service is not None:
        ollama_service.stop_ollama()


# Create Ollama client
def get_client() -> ollama.Client:
    """Create an Ollama client using the configured local service port."""

    port = settings.get("ollama-service_port", 30002)
    host = f"http://127.0.0.1:{port}"
    return ollama.Client(host=host)

# List local models
def get_models() -> list[dict[str, Any]]:
    """Return the locally available Ollama models."""

    client = get_client()
    try:
        response = client.list()
    except Exception as exc:
        logger.error("[Ollama API] Error listing models: %s", exc)
        return []

    if isinstance(response, dict):
        return response.get("models", [])

    return getattr(response, "models", []) or []

# Pull model from Ollama
def download_model(model_name: str, **kwargs: Any) -> Any:
    """Pull a model from Ollama."""

    client = get_client()
    stream = kwargs.get("stream", False)

    try:
        return client.pull(model_name, stream=stream)
    except Exception as exc:
        logger.error("[Ollama API] Error downloading model %s: %s", model_name, exc)
        raise

# Read model settings
def get_model_settings(model_name: str) -> Any:
    """Return metadata and Modelfile-style settings for an Ollama model."""

    client = get_client()
    try:
        return client.show(model_name)
    except Exception as exc:
        logger.error("[Ollama API] Error fetching settings for %s: %s", model_name, exc)
        raise


# Read SDK field
def _get_field(value: Any, *names: str, default: Any = None) -> Any:
    """Return the first matching field from dict-like or attribute objects."""

    for name in names:
        if isinstance(value, dict) and name in value:
            return value.get(name)
        if hasattr(value, name):
            return getattr(value, name)

    return default

# Normalize tool call
def _normalize_tool_call(raw_call: Any) -> dict[str, Any] | None:
    """Convert an Ollama tool-call payload into a predictable dictionary."""

    raw_function = _get_field(raw_call, "function", default=raw_call)
    name = str(_get_field(raw_function, "name", default="") or "").strip()
    if not name:
        return None

    arguments = _get_field(raw_function, "arguments", default={})
    if arguments is None:
        arguments = {}
    if isinstance(arguments, str):
        arguments = {"value": arguments}
    if not isinstance(arguments, dict):
        arguments = {"value": arguments}

    return {"name": name, "arguments": arguments}

# Merge streamed tool calls
def _merge_tool_calls(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge streamed tool-call chunks without duplicating entries."""

    merged = list(existing)
    for item in incoming:
        if item not in merged:
            merged.append(item)

    return merged

# Normalize assistant message
def _normalize_message(raw_message: Any) -> dict[str, Any]:
    """Convert an Ollama message object into a JSON-compatible dictionary."""

    if raw_message is None:
        return {"role": "assistant", "content": ""}

    role = str(_get_field(raw_message, "role", default="assistant") or "assistant")
    content = str(_get_field(raw_message, "content", default="") or "")
    thinking = str(_get_field(raw_message, "thinking", default="") or "")
    tool_calls = _get_field(raw_message, "tool_calls", "toolCalls", default=[]) or []

    normalized_message = {"role": role, "content": content}
    if thinking:
        normalized_message["thinking"] = thinking

    normalized_calls = []
    for raw_call in tool_calls:
        tool_call = _normalize_tool_call(raw_call)
        if tool_call:
            normalized_calls.append(
                {
                    "function": {
                        "name": tool_call["name"],
                        "arguments": tool_call["arguments"],
                    }
                }
            )

    if normalized_calls:
        normalized_message["tool_calls"] = normalized_calls

    return normalized_message

# Flatten chat options
def _prepare_chat_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Move supported top-level Ollama parameters out of nested options."""

    call_kwargs = {key: value for key, value in kwargs.items() if key not in OLLAMA_INTERNAL_CHAT_KEYS}
    options = call_kwargs.get("options")

    if isinstance(options, dict):
        for key in OLLAMA_TOP_LEVEL_CHAT_KEYS:
            if key in options:
                call_kwargs[key] = options.pop(key)

        if not options:
            call_kwargs.pop("options", None)

    think = kwargs.get("think")
    think_level = kwargs.get("think_level")
    if think is not None:
        if bool(think) and think_level in {"low", "medium", "high"}:
            call_kwargs["think"] = think_level
        else:
            call_kwargs["think"] = think

    return call_kwargs


# Build tool message
def _build_tool_message(
    tool_name: str,
    content: str,
    tool_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a tool message payload that can be fed back into Ollama."""

    payload = {
        "role": "tool",
        "name": tool_name,
        "tool_name": tool_name,
        "content": content,
    }

    if tool_event:
        payload.update(
            {
                "server_id": tool_event.get("server_id") or "",
                "server_name": tool_event.get("server_name") or "",
                "tool_id": tool_event.get("tool_id") or tool_name,
                "tool_display_name": tool_event.get("tool_name") or tool_name,
                "arguments": tool_event.get("arguments") or {},
            }
        )

    return payload

# Build tool event
def _build_tool_event(tool_lookup: dict[str, dict[str, Any]], tool_call: dict[str, Any]) -> dict[str, Any]:
    """Serialize one tool invocation so the UI can render it during streaming."""

    alias = tool_call.get("name", "")
    lookup_entry = tool_lookup.get(alias, {})
    server_definition = lookup_entry.get("server", {})
    tool_definition = lookup_entry.get("tool", {})

    return {
        "alias": alias,
        "server_id": server_definition.get("id") or "",
        "server_name": server_definition.get("name") or server_definition.get("id") or "",
        "tool_id": tool_definition.get("id") or alias,
        "tool_name": tool_definition.get("name") or alias,
        "arguments": tool_call.get("arguments") or {},
    }


# Stream one model round
def _stream_round(
    client: ollama.Client,
    model_name: str,
    conversation: list[dict[str, Any]],
    base_kwargs: dict[str, Any],
    tools: list[dict[str, Any]] | None = None,
):
    """Stream one Ollama round and return the assembled assistant message."""

    assistant_message: dict[str, Any] = {"role": "assistant", "content": ""}
    thinking_buffer = ""
    tool_calls: list[dict[str, Any]] = []
    yielded_visible_chunk = False

    stream_kwargs = dict(base_kwargs)
    if tools:
        stream_kwargs["tools"] = tools

    for raw_chunk in client.chat(model=model_name, messages=conversation, stream=True, **stream_kwargs):
        normalized_chunk = _normalize_message(_get_field(raw_chunk, "message", default=raw_chunk))
        thinking_part = normalized_chunk.get("thinking", "") or ""
        content_part = normalized_chunk.get("content", "") or ""
        incoming_tool_calls = [
            _normalize_tool_call(raw_call)
            for raw_call in normalized_chunk.get("tool_calls", [])
        ]
        incoming_tool_calls = [tool_call for tool_call in incoming_tool_calls if tool_call]

        # Keep the final message while streaming visible chunks.
        if thinking_part:
            thinking_buffer += thinking_part
        if content_part:
            assistant_message["content"] += content_part
        if incoming_tool_calls:
            tool_calls = _merge_tool_calls(tool_calls, incoming_tool_calls)

        if thinking_part or content_part:
            yielded_visible_chunk = True
            chunk_payload = {"role": "assistant", "content": content_part}
            if thinking_part:
                chunk_payload["thinking"] = thinking_part
            yield {"message": chunk_payload}

    if thinking_buffer:
        assistant_message["thinking"] = thinking_buffer
    if tool_calls:
        assistant_message["tool_calls"] = [
            {"function": {"name": call["name"], "arguments": call["arguments"]}}
            for call in tool_calls
        ]

    if not yielded_visible_chunk and (assistant_message.get("thinking") or assistant_message.get("content")):
        yield {"message": assistant_message}

    return assistant_message

# Drain streamed round
def _yield_stream_round(round_stream):
    """Yield every chunk from a round stream and return the final assistant message."""

    while True:
        try:
            yield next(round_stream)
        except StopIteration as stop:
            return stop.value or {"role": "assistant", "content": ""}

# Run tool loop
def _run_tool_loop(
    client: ollama.Client,
    model_name: str,
    messages: list[dict[str, Any]],
    call_kwargs: dict[str, Any],
    tool_server_id: str,
    tool_context: dict[str, Any],
):
    """Resolve local tools through Ollama tool-calling with streaming output."""

    tools, tool_lookup = tool_registry.build_ollama_tools(
        tool_server_id,
        engine="ollama-service",
        model_name=model_name,
    )
    base_kwargs = {key: value for key, value in call_kwargs.items() if key != "stream"}

    if not tools:
        yield from _yield_stream_round(_stream_round(client, model_name, messages, base_kwargs))
        return

    conversation = [dict(message) for message in messages]

    for round_index in range(MAX_TOOL_ROUNDS):
        assistant_message = yield from _yield_stream_round(
            _stream_round(client, model_name, conversation, base_kwargs, tools=tools)
        )
        conversation.append(assistant_message)

        # Tool calls may arrive in parts, so normalize the final payload again.
        tool_calls = [
            _normalize_tool_call(raw_call)
            for raw_call in assistant_message.get("tool_calls", [])
        ]
        tool_calls = [tool_call for tool_call in tool_calls if tool_call]

        yield {"transcript_message": assistant_message}

        if not tool_calls:
            return

        for tool_call_index, tool_call in enumerate(tool_calls, start=1):
            tool_event = _build_tool_event(tool_lookup, tool_call)
            yield {"tool_event": tool_event}

            call_context = dict(tool_context or {})
            call_context.update(
                {
                    "tool_alias": tool_call["name"],
                    "tool_arguments": tool_call.get("arguments") or {},
                    "tool_call_index": tool_call_index,
                    "tool_round_index": round_index + 1,
                }
            )

            tool_result = tool_registry.call_ollama_tool(
                tool_lookup,
                tool_call["name"],
                tool_call.get("arguments") or {},
                context=call_context,
            )
            tool_message = _build_tool_message(tool_call["name"], tool_result, tool_event)

            conversation.append(tool_message)
            yield {"tool_result": tool_message}

    yield {"message": {"content": "[Error during generation: tool loop exceeded the safety limit.]"}}

# Generate Ollama response
def generate(model_name: str, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
    """Generate a chat response through Ollama."""

    client = get_client()
    tool_server_id = str(kwargs.pop("tool_server_id", kwargs.pop("tool_id", "")) or "").strip()
    tool_context = dict(kwargs.pop("tool_context", {}) or {})

    try:
        call_kwargs = _prepare_chat_kwargs(kwargs)

        if tool_server_id:
            return _run_tool_loop(client, model_name, messages, call_kwargs, tool_server_id, tool_context)

        return client.chat(model=model_name, messages=messages, **call_kwargs)
    except Exception as exc:
        logger.error("[Ollama API] Error generating response from %s: %s", model_name, exc)
        raise
