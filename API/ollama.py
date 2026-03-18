"""Ollama adapter used by the generic LLM registry."""

from __future__ import annotations

import logging
from typing import Any

import ollama

from API import mcp as tool_registry
from Settings import settings

logger = logging.getLogger(__name__)

OLLAMA_TOP_LEVEL_CHAT_KEYS = {"format", "keep_alive", "logprobs", "top_logprobs"}
MAX_TOOL_ROUNDS = 6


def prepare_runtime() -> None:
    """Ensure the managed Ollama runtime is available before a request is sent."""
    try:
        import importlib

        ollama_service = importlib.import_module("Services.ollama-service")
        ollama_service.start_ollama()
    except ImportError as exc:
        logger.warning("[Ollama API] Could not import Services.ollama-service: %s", exc)


def cleanup_runtime() -> None:
    """Stop the managed Ollama runtime when the engine is deselected."""
    try:
        import importlib

        ollama_service = importlib.import_module("Services.ollama-service")
        ollama_service.stop_ollama()
    except ImportError as exc:
        logger.warning("[Ollama API] Could not import Services.ollama-service: %s", exc)


def get_client() -> ollama.Client:
    """Create an Ollama client using the configured local service port."""
    port = settings.get("ollama-service_port", 30002)
    host = f"http://127.0.0.1:{port}"
    return ollama.Client(host=host)


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


def download_model(model_name: str, **kwargs: Any) -> Any:
    """Pull a model from Ollama."""
    client = get_client()
    stream = kwargs.get("stream", False)
    try:
        return client.pull(model_name, stream=stream)
    except Exception as exc:
        logger.error("[Ollama API] Error downloading model %s: %s", model_name, exc)
        raise


def _get_field(value: Any, *names: str, default: Any = None) -> Any:
    """Return the first present field from a dict-like or attribute-based object."""
    for name in names:
        if isinstance(value, dict) and name in value:
            return value.get(name)
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _normalize_tool_call(raw_call: Any) -> dict[str, Any] | None:
    """Convert an Ollama tool call payload to a predictable dict."""
    raw_function = _get_field(raw_call, 'function', default=raw_call)
    name = str(_get_field(raw_function, 'name', default='') or '').strip()
    if not name:
        return None

    arguments = _get_field(raw_function, 'arguments', default={})
    if arguments is None:
        arguments = {}
    if isinstance(arguments, str):
        arguments = {'value': arguments}
    if not isinstance(arguments, dict):
        arguments = {'value': arguments}

    return {
        'name': name,
        'arguments': arguments,
    }


def _normalize_message(raw_message: Any) -> dict[str, Any]:
    """Convert an Ollama message object into a JSON-compatible dict."""
    if raw_message is None:
        return {'role': 'assistant', 'content': ''}

    role = str(_get_field(raw_message, 'role', default='assistant') or 'assistant')
    content = str(_get_field(raw_message, 'content', default='') or '')
    thinking = str(_get_field(raw_message, 'thinking', default='') or '')
    tool_calls = _get_field(raw_message, 'tool_calls', 'toolCalls', default=[]) or []

    normalized = {
        'role': role,
        'content': content,
    }
    if thinking:
        normalized['thinking'] = thinking

    normalized_calls = []
    for raw_call in tool_calls:
        tool_call = _normalize_tool_call(raw_call)
        if tool_call:
            normalized_calls.append(
                {
                    'function': {
                        'name': tool_call['name'],
                        'arguments': tool_call['arguments'],
                    }
                }
            )

    if normalized_calls:
        normalized['tool_calls'] = normalized_calls

    return normalized


def _prepare_chat_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Move supported top-level Ollama parameters out of the nested options dict."""
    call_kwargs = {key: value for key, value in kwargs.items() if key not in {'system', 'prompt', 'tool_id', 'tool_context'}}
    options = call_kwargs.get('options')

    if isinstance(options, dict):
        for key in OLLAMA_TOP_LEVEL_CHAT_KEYS:
            if key in options:
                call_kwargs[key] = options.pop(key)

        if not options:
            call_kwargs.pop('options', None)

    think = kwargs.get('think')
    think_level = kwargs.get('think_level')
    if think is not None:
        if bool(think) and think_level in {'low', 'medium', 'high'}:
            call_kwargs['think'] = think_level
        else:
            call_kwargs['think'] = think

    return call_kwargs


def _build_tool_message(tool_name: str, content: str) -> dict[str, Any]:
    """Build a tool message payload that Ollama can feed back into the chat loop."""
    return {
        'role': 'tool',
        'name': tool_name,
        'tool_name': tool_name,
        'content': content,
    }


def _run_tool_loop(
    client: ollama.Client,
    model_name: str,
    messages: list[dict[str, Any]],
    call_kwargs: dict[str, Any],
    tool_id: str,
    tool_context: dict[str, Any],
):
    """Resolve a selected local tool through Ollama tool calling."""
    tools, tool_lookup = tool_registry.build_ollama_tools(tool_id, engine='ollama-service', model_name=model_name)
    if not tools:
        response = client.chat(model=model_name, messages=messages, stream=False, **call_kwargs)
        yield {'message': _normalize_message(_get_field(response, 'message', default=response))}
        return

    conversation = [dict(message) for message in messages]
    base_kwargs = {key: value for key, value in call_kwargs.items() if key != 'stream'}

    for _round in range(MAX_TOOL_ROUNDS):
        response = client.chat(
            model=model_name,
            messages=conversation,
            stream=False,
            tools=tools,
            **base_kwargs,
        )
        assistant_message = _normalize_message(_get_field(response, 'message', default=response))
        conversation.append(assistant_message)

        tool_calls = [
            _normalize_tool_call(raw_call)
            for raw_call in assistant_message.get('tool_calls', [])
        ]
        tool_calls = [tool_call for tool_call in tool_calls if tool_call]

        if not tool_calls:
            yield {'message': assistant_message}
            return

        for tool_call in tool_calls:
            tool_result = tool_registry.call_ollama_tool(
                tool_lookup,
                tool_call['name'],
                tool_call.get('arguments') or {},
                context=tool_context,
            )
            conversation.append(_build_tool_message(tool_call['name'], tool_result))

    yield {'message': {'content': '[Error during generation: tool loop exceeded the safety limit.]'}}


def generate(model_name: str, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
    """Generate a chat response through Ollama."""
    client = get_client()
    tool_id = str(kwargs.pop('tool_id', '') or '').strip()
    tool_context = dict(kwargs.pop('tool_context', {}) or {})

    try:
        call_kwargs = _prepare_chat_kwargs(kwargs)

        if tool_id:
            return _run_tool_loop(client, model_name, messages, call_kwargs, tool_id, tool_context)

        return client.chat(model=model_name, messages=messages, **call_kwargs)
    except Exception as exc:
        logger.error("[Ollama API] Error generating response from %s: %s", model_name, exc)
        raise


def get_model_settings(model_name: str) -> Any:
    """Return metadata and Modelfile-style settings for an Ollama model."""
    client = get_client()
    try:
        return client.show(model_name)
    except Exception as exc:
        logger.error("[Ollama API] Error fetching settings for %s: %s", model_name, exc)
        raise
