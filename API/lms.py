# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import json
import logging
import threading
from typing import Any
from urllib.parse import urlparse

from API import mcp as tool_registry
from Settings import settings

logger = logging.getLogger(__name__)

# Global abort event — set to interrupt the active generation immediately.
_abort_event = threading.Event()


def abort_generation() -> None:
    """Signal the active LM Studio generation to stop."""
    _abort_event.set()


INTERNAL_CHAT_KEYS = {"system", "prompt", "tool_id", "tool_server_id", "tool_server_ids", "tool_context", "think", "think_level", "engine"}
MAX_TOOL_ROUNDS = 100


# Clean saved load config
def _get_load_config() -> dict[str, Any]:
    """Return the saved LM Studio load config without empty values."""

    raw_config = settings.get("lms_load_config", {}) or {}
    if not isinstance(raw_config, dict):
        return {}

    def _clean(value: Any) -> Any:
        """Recursively drop empty values from nested config structures."""

        if isinstance(value, dict):
            cleaned_items: dict[str, Any] = {}
            for key, item in value.items():
                cleaned_item = _clean(item)
                if cleaned_item is not None:
                    cleaned_items[key] = cleaned_item
            return cleaned_items or None

        if isinstance(value, list):
            return value or None

        if value in ("", None):
            return None

        return value

    cleaned_config = _clean(raw_config)
    return cleaned_config if isinstance(cleaned_config, dict) else {}

# Parse LM Studio host
def _extract_api_host(raw_address: str) -> str:
    """Normalize the configured LM Studio address into a client host value."""

    parsed = urlparse(raw_address)

    if parsed.scheme and parsed.netloc:
        return parsed.netloc

    if parsed.scheme and parsed.path:
        return parsed.path

    return raw_address.strip().rstrip("/")


# Import LM Studio SDK
def _get_sdk():
    """Import the LM Studio SDK lazily so the app can boot without it."""

    try:
        import lmstudio as lms
    except ImportError as exc:
        raise ImportError("The 'lmstudio' package is required for LM Studio support.") from exc

    return lms

# Create LM Studio client
def _get_client():
    """Create a fresh LM Studio client for the configured server."""

    lms = _get_sdk()
    api_host = _extract_api_host(settings.get_engine_url("lms"))
    return lms, lms.Client(api_host)

# Close LM Studio client
def _close_client(client: Any) -> None:
    """Safely close a client instance when the SDK exposes ``close``."""

    try:
        client.close()
    except Exception:
        pass


# Build model handle
def _get_model_handle(client: Any, model_name: str):
    """Create a model handle with the current persisted load config."""

    load_config = _get_load_config()
    if load_config:
        return client.llm.model(model_name, config=load_config)

    return client.llm.model(model_name)

# Extract model name
def _coerce_model_name(entry: Any) -> str:
    """Extract a stable model identifier from LM Studio SDK objects."""

    for attr_name in ("model_key", "model", "identifier", "id", "display_name"):
        value = getattr(entry, attr_name, None)
        if value:
            return str(value)

    get_info = getattr(entry, "get_info", None)
    if not callable(get_info):
        return ""

    try:
        info = get_info()
    except Exception:
        return ""

    if hasattr(info, "to_dict"):
        info = info.to_dict()

    if not isinstance(info, dict):
        return ""

    for key in ("model_key", "modelKey", "display_name", "displayName", "identifier", "id"):
        value = info.get(key)
        if value:
            return str(value)

    return ""

# Deduplicate model names
def _collect_unique_model_names(entries: list[Any]) -> list[str]:
    """Return unique model names while preserving the original order."""

    unique_names: list[str] = []
    seen_names: set[str] = set()

    for entry in entries:
        model_name = _coerce_model_name(entry)
        if not model_name or model_name in seen_names:
            continue

        seen_names.add(model_name)
        unique_names.append(model_name)

    return unique_names

# Call LM Studio list method
def _list_models_with_client(method_name: str) -> list[Any]:
    """Call one LM Studio listing method and always close the client."""

    _lms, client = _get_client()

    try:
        return list(getattr(client, method_name)())
    finally:
        _close_client(client)


# Build chat history (lmstudio SDK — no tool support)
def _build_chat_history(lms, messages: list[dict[str, Any]]):
    """Convert generic chat messages into an LM Studio chat history."""

    chat = lms.Chat()

    for message in messages:
        role = str(message.get("role", "user")).lower()
        content = message.get("content", "") or ""
        images = message.get("images") or []

        if images:
            raise NotImplementedError("LM Studio image inputs are not implemented yet.")

        if role == "system":
            chat.add_system_prompt(content)
            continue

        if role == "assistant":
            chat.add_assistant_response(content)
            continue

        chat.add_user_message(content)

    return chat


# Create OpenAI-compatible client for LM Studio tool-calling flows
def _get_openai_client():
    """Create an OpenAI client pointing at the LM Studio server."""

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("The 'openai' package is required for LM Studio tool support.") from exc

    raw_url = settings.get_engine_url("lms")
    # Ensure the URL has a scheme and /v1 suffix for OpenAI compatibility.
    if not raw_url.startswith("http"):
        raw_url = f"http://{raw_url}"
    if not raw_url.rstrip("/").endswith("/v1"):
        raw_url = raw_url.rstrip("/") + "/v1"

    return OpenAI(base_url=raw_url, api_key="lm-studio")


# Build OpenAI-compatible messages for tool-calling flows
def _build_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert ASLM chat messages into OpenAI-compatible payloads."""

    payload: list[dict[str, Any]] = []

    for message in messages:
        role = str(message.get("role", "user")).lower()
        content = message.get("content", "") or ""

        if role == "tool":
            payload.append({
                "role": "tool",
                "tool_call_id": message.get("tool_call_id", message.get("name", "call")),
                "content": content,
            })
            continue

        if role == "assistant":
            entry: dict[str, Any] = {"role": "assistant", "content": content}
            if message.get("tool_calls"):
                entry["tool_calls"] = message["tool_calls"]
            payload.append(entry)
            continue

        payload.append({"role": role, "content": content})

    return payload


# Build tool event for UI
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


# Build tool result message for the conversation
def _build_tool_message(
    tool_name: str,
    tool_call_id: str,
    content: str | dict[str, Any],
    tool_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a tool message payload for the OpenAI-compatible conversation."""

    payload: dict[str, Any] = {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": content if isinstance(content, str) else str(content),
    }

    if tool_event:
        payload.update({
            "alias": tool_event.get("alias") or tool_name,
            "server_id": tool_event.get("server_id") or "",
            "server_name": tool_event.get("server_name") or "",
            "tool_id": tool_event.get("tool_id") or tool_name,
            "tool_display_name": tool_event.get("tool_name") or tool_name,
            "arguments": tool_event.get("arguments") or {},
        })

    return payload


# Stream one OpenAI-compatible round with tool support
def _stream_openai_round(
    client,
    model_name: str,
    conversation: list[dict[str, Any]],
    options: dict[str, Any],
    tools: list[dict[str, Any]] | None = None,
):
    """Stream one LM Studio round via OpenAI API and return the assembled message."""

    request_kwargs: dict[str, Any] = dict(options)
    if tools:
        request_kwargs["tools"] = tools
        request_kwargs["tool_choice"] = "auto"

    assistant_content = ""
    tool_calls_by_index: dict[int, dict[str, Any]] = {}

    for chunk in client.chat.completions.create(
        model=model_name,
        messages=conversation,
        stream=True,
        **request_kwargs,
    ):
        if _abort_event.is_set():
            break

        for choice in getattr(chunk, "choices", []) or []:
            delta = getattr(choice, "delta", None)
            if not delta:
                continue

            content_part = getattr(delta, "content", "") or ""
            if content_part:
                assistant_content += content_part
                yield {"message": {"content": content_part}}

            # Accumulate streamed tool call fragments.
            for tc in getattr(delta, "tool_calls", []) or []:
                idx = getattr(tc, "index", 0)
                if idx not in tool_calls_by_index:
                    tool_calls_by_index[idx] = {
                        "id": getattr(tc, "id", "") or "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                entry = tool_calls_by_index[idx]
                if getattr(tc, "id", None):
                    entry["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn:
                    if getattr(fn, "name", None):
                        entry["function"]["name"] += fn.name
                    if getattr(fn, "arguments", None):
                        entry["function"]["arguments"] += fn.arguments

    # Build the final assistant message.
    assembled_tool_calls = []
    for idx in sorted(tool_calls_by_index):
        assembled_tool_calls.append(tool_calls_by_index[idx])

    assistant_message: dict[str, Any] = {"role": "assistant", "content": assistant_content}
    if assembled_tool_calls:
        assistant_message["tool_calls"] = assembled_tool_calls

    return assistant_message


# Drain streamed round
def _yield_stream_round(round_stream):
    """Yield every chunk from a round stream and return the final assistant message."""

    while True:
        try:
            yield next(round_stream)
        except StopIteration as stop:
            return stop.value or {"role": "assistant", "content": ""}


# Run tool loop via OpenAI-compatible API
def _run_tool_loop(
    client,
    model_name: str,
    messages: list[dict[str, Any]],
    options: dict[str, Any],
    tool_server_ids: list[str],
    tool_context: dict[str, Any],
):
    """Resolve local tools through LM Studio OpenAI-compatible tool-calling."""

    tools, tool_lookup = tool_registry.build_ollama_tools(
        tool_server_ids,
        engine="lms",
        model_name=model_name,
    )

    if not tools:
        yield from _yield_stream_round(
            _stream_openai_round(client, model_name, _build_openai_messages(messages), options)
        )
        return

    conversation = _build_openai_messages(messages)

    for round_index in range(MAX_TOOL_ROUNDS):
        assistant_message = yield from _yield_stream_round(
            _stream_openai_round(client, model_name, conversation, options, tools=tools)
        )
        conversation.append(assistant_message)

        raw_tool_calls = assistant_message.get("tool_calls") or []
        if not raw_tool_calls:
            return

        # Normalize into [{name, arguments, id}]
        tool_calls = []
        for tc in raw_tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                arguments = json.loads(fn.get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                arguments = {}
            tool_calls.append({
                "name": name,
                "arguments": arguments,
                "id": tc.get("id", f"call_{round_index}_{name}"),
            })

        yield {"transcript_message": assistant_message}

        for tool_call_index, tool_call in enumerate(tool_calls, start=1):
            tool_event = _build_tool_event(tool_lookup, tool_call)
            yield {"tool_event": tool_event}

            call_context = dict(tool_context or {})
            call_context.update({
                "engine": "lms",
                "model_name": model_name,
                "tool_alias": tool_call["name"],
                "tool_arguments": tool_call.get("arguments") or {},
                "tool_call_index": tool_call_index,
                "tool_round_index": round_index + 1,
            })

            tool_result = tool_registry.call_ollama_tool(
                tool_lookup,
                tool_call["name"],
                tool_call.get("arguments") or {},
                context=call_context,
            )

            # Image payloads are not supported via OpenAI messages — serialize to text.
            if isinstance(tool_result, dict) and "_image_b64" in tool_result:
                tool_result = f"[Image: {tool_result.get('_path', 'image')}]"

            tool_message = _build_tool_message(
                tool_call["name"],
                tool_call["id"],
                tool_result,
                tool_event,
            )
            conversation.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": tool_message["content"],
            })

            ui_tool_message = dict(tool_message)
            yield {"tool_result": ui_tool_message}

    yield {"message": {"content": "[Error during generation: tool loop exceeded the safety limit.]"}}


# List available models
def get_models() -> list[Any]:
    """Return models visible to the configured LM Studio server."""

    try:
        downloaded_models = _list_models_with_client("list_downloaded_models")
    except Exception as exc:
        logger.error("[LM Studio API] Error listing downloaded models: %s", exc)
        return []

    # Prefer the local downloaded catalog when it is available.
    merged_models = _collect_unique_model_names(downloaded_models)
    if merged_models:
        return merged_models

    try:
        loaded_models = _list_models_with_client("list_loaded_models")
    except Exception as exc:
        logger.error("[LM Studio API] Error listing loaded models: %s", exc)
        return []

    return _collect_unique_model_names(loaded_models)

# Unload loaded models
def cleanup_runtime() -> None:
    """Unload every currently loaded LM Studio model."""

    try:
        loaded_models = _list_models_with_client("list_loaded_models")
    except Exception as exc:
        logger.warning("[LM Studio API] Could not list loaded models for unload: %s", exc)
        return

    for entry in loaded_models:
        # Use the loaded handle first when the SDK already gives one.
        unload = getattr(entry, "unload", None)
        if callable(unload):
            try:
                unload()
                continue
            except Exception as exc:
                logger.warning("[LM Studio API] Failed to unload model via handle: %s", exc)

        # Fall back to a fresh handle when only metadata was returned.
        model_name = _coerce_model_name(entry)
        if not model_name:
            continue

        _lms, client = _get_client()
        try:
            handle = client.llm.model(model_name)
            unload = getattr(handle, "unload", None)
            if callable(unload):
                unload()
        except Exception as exc:
            logger.warning("[LM Studio API] Failed to unload model %s: %s", model_name, exc)
        finally:
            _close_client(client)

# Reload selected model
def reload_model(model_name: str) -> None:
    """Unload all models and reload the selected one with current settings."""

    if not model_name:
        return

    cleanup_runtime()

    _lms, client = _get_client()
    try:
        model = _get_model_handle(client, model_name)

        # Touch the model so the new load config is applied immediately.
        get_context_length = getattr(model, "get_context_length", None)
        if callable(get_context_length):
            get_context_length()
    finally:
        _close_client(client)

# Reject local download request
def download_model(model_name: str, **kwargs: Any) -> Any:
    """Raise because LM Studio downloads are managed outside this adapter."""

    raise NotImplementedError("LM Studio model downloads are managed by LM Studio.")


# Generate LM Studio response
def generate(model_name: str, messages: list[dict[str, Any]], **kwargs: Any):
    """Generate a streamed or non-streamed response through LM Studio.

    When *tool_server_ids* are provided the request is routed through the
    OpenAI-compatible endpoint so that function-calling works.  Plain text
    generation still uses the native LM Studio SDK.
    """

    raw_ids = kwargs.pop("tool_server_ids", None) or kwargs.pop("tool_server_id", None) or kwargs.pop("tool_id", None)
    if isinstance(raw_ids, str):
        tool_server_ids = [raw_ids] if raw_ids.strip() else []
    elif isinstance(raw_ids, list):
        tool_server_ids = [str(s) for s in raw_ids if str(s).strip()]
    else:
        tool_server_ids = []
    tool_context = dict(kwargs.pop("tool_context", {}) or {})

    _abort_event.clear()

    # Route through OpenAI-compatible API when tools are requested.
    if tool_server_ids:
        openai_client = _get_openai_client()
        options = dict(kwargs.get("options", {}) or {})
        # Strip internal keys that are not valid OpenAI parameters.
        for key in list(INTERNAL_CHAT_KEYS):
            options.pop(key, None)
            kwargs.pop(key, None)
        return _run_tool_loop(openai_client, model_name, messages, options, tool_server_ids, tool_context)

    # Plain text generation via native lmstudio SDK.
    lms, client = _get_client()
    chat = _build_chat_history(lms, messages)
    options = kwargs.get("options", {}) or {}
    stream = bool(kwargs.get("stream", False))

    try:
        model = _get_model_handle(client, model_name)

        if stream:
            for fragment in model.respond_stream(chat, config=options or None):
                if _abort_event.is_set():
                    break
                content = getattr(fragment, "content", "") or ""
                if content:
                    yield {"message": {"content": content}}
            return

        result = model.respond(chat, config=options or None)
        content = getattr(result, "content", "") or ""
        if content:
            yield {"message": {"content": content}}
    except Exception as exc:
        logger.error("[LM Studio API] Error generating response from %s: %s", model_name, exc)
        raise
    finally:
        _close_client(client)

# Return generic model metadata
def get_model_settings(model_name: str) -> dict[str, Any]:
    """Return generic capability metadata without forcing a model load."""

    info_payload: dict[str, Any] = {"model": model_name}
    capabilities: list[str] = ["tools"]

    return {
        "model": model_name,
        "context_length": 8192,
        "defaults": {},
        "supports_thinking": False,
        "supports_think_level": False,
        "supports_vision": False,
        "supports_tool_calling": True,
        "capabilities": capabilities,
        "raw": info_payload,
    }
