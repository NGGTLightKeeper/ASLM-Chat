# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import importlib
import inspect
import logging
import re
from types import ModuleType
from typing import Any

from API import mcp as tool_registry
from Settings import settings
from Tools.system_prompts import CHAT_TITLE_INSTRUCTIONS

logger = logging.getLogger(__name__)

ENGINE_MODULES = {
    "ollama": "API.ollama",
    "ollama-service": "API.ollama",
    "lms": "API.lms",
    "lm-studio": "API.lms",
    "openai": "API.openai",
    "openai-api": "API.openai",
    "google-genai": "API.google_genai",
    "google_genai": "API.google_genai",
    "google": "API.google_genai",
    "gemini": "API.google_genai",
}

CHAT_TITLE_SOURCE_LIMIT = 2048
CHAT_TITLE_OUTPUT_LIMIT = 32
CHAT_TITLE_REASONING_OUTPUT_LIMIT = 1024
CHAT_TITLE_CONTEXT_LIMIT = 4096
CHAT_TITLE_LENGTH_LIMIT = 255
REASONING_LEVEL_ORDER = ("minimal", "low", "medium", "high", "xhigh")
REASONING_TAG_PAIRS = (
    ("<think>", "</think>"),
    ("<thinking>", "</thinking>"),
    ("<reasoning>", "</reasoning>"),
)


# Resolve the engine adapter module.
def _get_engine_module(engine: str | None) -> ModuleType:
    """Load the adapter module for the selected LLM engine."""

    canonical_engine = settings.normalize_engine_name(engine)
    module_name = ENGINE_MODULES.get(canonical_engine)

    if not module_name:
        raise ValueError(f"Unsupported LLM engine: {engine}")

    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        logger.error("Failed to load engine module %s: %s", module_name, exc)
        raise ImportError(f"Failed to load engine module {module_name}: {exc}") from exc


# List models exposed by one engine.
def get_models(engine: str | None) -> Any:
    """Return the list of models exposed by the selected engine."""

    prepare_runtime(engine)
    module = _get_engine_module(engine)
    if hasattr(module, "get_models"):
        return module.get_models()

    raise NotImplementedError(f"Engine {engine} does not implement get_models")


# Download a model through one engine.
def download_model(engine: str | None, model_name: str, **kwargs: Any) -> Any:
    """Download or pull a model through the selected engine adapter."""

    prepare_runtime(engine)
    module = _get_engine_module(engine)
    if hasattr(module, "download_model"):
        return module.download_model(model_name, **kwargs)

    raise NotImplementedError(f"Engine {engine} does not implement download_model")


# Generate a response through one engine.
def generate(engine: str | None, model_name: str, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
    """Generate a chat response through the selected engine adapter."""

    module = _get_engine_module(engine)
    if hasattr(module, "generate"):
        return module.generate(model_name, messages, **kwargs)

    raise NotImplementedError(f"Engine {engine} does not implement generate")


# Return visible content from one normalized adapter chunk.
def _extract_chat_title_chunk(chunk: Any) -> str:
    raw_message = chunk.get("message", {}) if isinstance(chunk, dict) else getattr(chunk, "message", {})
    if isinstance(raw_message, dict):
        return str(raw_message.get("content", "") or "")
    return str(getattr(raw_message, "content", "") or "")


# Clean one generated title before it is persisted or returned in a header.
def _sanitize_chat_title(title: str) -> str:
    cleaned = str(title or "")
    for start_tag, end_tag in REASONING_TAG_PAIRS:
        while True:
            start_index = cleaned.lower().find(start_tag)
            if start_index < 0:
                break
            end_index = cleaned.lower().find(end_tag, start_index + len(start_tag))
            if end_index < 0:
                cleaned = cleaned[:start_index]
                break
            cleaned = cleaned[:start_index] + cleaned[end_index + len(end_tag):]

    cleaned = re.sub(r"<\|[^>]+\|>", "", cleaned)
    cleaned = " ".join(cleaned.split()).strip(" `\"'“”‘’#")
    if cleaned.lower().startswith("[error during generation:"):
        return ""
    return cleaned[:CHAT_TITLE_LENGTH_LIMIT].rstrip()


# Generate a title through the selected model without touching chat history.
def generate_chat_title(
    engine: str | None,
    model_name: str,
    user_message: str,
    model_info: dict[str, Any] | None = None,
) -> str:
    """Return a generated title or an empty string when the fallback should be used."""

    source = str(user_message or "").strip()[:CHAT_TITLE_SOURCE_LIMIT]
    if not source:
        return ""

    canonical_engine = settings.normalize_engine_name(engine)
    model_info = model_info if isinstance(model_info, dict) else {}
    supports_think_toggle = bool(model_info.get("supports_think_toggle", False))
    supports_think_level = bool(model_info.get("supports_think_level", False))
    supports_thinking = bool(
        model_info.get("supports_thinking", False)
        or supports_think_toggle
        or supports_think_level
    )
    advertised_levels = [
        str(level).strip().lower()
        for level in model_info.get("think_level_options", [])
        if str(level).strip()
    ]
    lowest_level = next(
        (level for level in REASONING_LEVEL_ORDER if level in advertised_levels),
        advertised_levels[0] if advertised_levels else "low",
    )
    reasoning_level = lowest_level if supports_think_level or canonical_engine == "google-genai" else None

    attempts: list[tuple[bool, str | None, int]] = []
    if supports_thinking and supports_think_toggle:
        attempts.append((True, None, CHAT_TITLE_OUTPUT_LIMIT))
        attempts.append((False, reasoning_level, CHAT_TITLE_REASONING_OUTPUT_LIMIT))
    elif supports_thinking:
        attempts.append((False, reasoning_level, CHAT_TITLE_REASONING_OUTPUT_LIMIT))
    else:
        attempts.append((False, None, CHAT_TITLE_OUTPUT_LIMIT))
        attempts.append((False, reasoning_level, CHAT_TITLE_REASONING_OUTPUT_LIMIT))

    messages = [
        {"role": "system", "content": CHAT_TITLE_INSTRUCTIONS},
        {"role": "user", "content": source},
    ]
    supported_parameters = {
        str(name).strip()
        for name in model_info.get("supported_parameters", [])
        if str(name).strip()
    }

    for disable_thinking, think_level, output_limit in attempts:
        options: dict[str, Any]
        if settings.is_ollama_engine(canonical_engine):
            context_length = model_info.get("context_length", CHAT_TITLE_CONTEXT_LIMIT)
            try:
                context_limit = min(max(int(context_length), 1), CHAT_TITLE_CONTEXT_LIMIT)
            except (TypeError, ValueError):
                context_limit = CHAT_TITLE_CONTEXT_LIMIT
            options = {"num_ctx": context_limit, "num_predict": output_limit}
        elif canonical_engine == "lms":
            options = {"maxTokens": output_limit}
        elif canonical_engine == "google-genai":
            options = {"max_output_tokens": output_limit}
        else:
            token_option = (
                "max_completion_tokens"
                if "max_completion_tokens" in supported_parameters
                else "max_tokens"
            )
            options = {token_option: output_limit}

        generate_kwargs: dict[str, Any] = {
            "engine": canonical_engine,
            "model_name": model_name,
            "messages": messages,
            "options": options,
            "stream": True,
        }
        if disable_thinking:
            if canonical_engine == "google-genai":
                options["thinking_budget"] = 0
            else:
                generate_kwargs["think"] = False
                generate_kwargs["think_param_name"] = str(model_info.get("think_param_name", "think") or "think")
        elif think_level:
            if canonical_engine == "google-genai":
                options["thinking_level"] = think_level
            else:
                generate_kwargs["think_level"] = think_level
                generate_kwargs["think_level_param_name"] = str(
                    model_info.get("think_level_param_name", "think_level") or "think_level"
                )
        try:
            visible_parts = [
                _extract_chat_title_chunk(chunk)
                for chunk in generate(**generate_kwargs)
            ]
        except Exception as exc:
            logger.debug("Chat title generation failed for %s through %s: %s", model_name, canonical_engine, exc)
            continue

        title = _sanitize_chat_title("".join(visible_parts))
        if title:
            return title

    return ""


# Abort active generation for one engine or all loaded engines.
def abort_generation(engine: str | None = None, *, generation_id: str | None = None) -> None:
    """Signal the active generation for one engine or every loaded adapter."""

    tool_registry.abort_active_tools(generation_id)
    if engine is None:
        module_names = {module_name for module_name in ENGINE_MODULES.values()}
        for module_name in module_names:
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                continue

            abort = getattr(module, "abort_generation", None)
            if callable(abort):
                abort()
        return

    module = _get_engine_module(engine)
    abort = getattr(module, "abort_generation", None)
    if callable(abort):
        abort()


# Read model metadata from one engine.
def get_model_settings(engine: str | None, model_name: str) -> Any:
    """Return model metadata exposed by the selected engine."""

    prepare_runtime(engine)
    module = _get_engine_module(engine)
    if hasattr(module, "get_model_settings"):
        return module.get_model_settings(model_name)

    raise NotImplementedError(f"Engine {engine} does not implement get_model_settings")


# Reload one model when the adapter supports it.
def reload_model(engine: str | None, model_name: str) -> None:
    """Reload the selected model when the engine supports explicit reloads."""

    module = _get_engine_module(engine)
    reload_func = getattr(module, "reload_model", None)
    if callable(reload_func):
        reload_func(model_name)
        return

    raise NotImplementedError(f"Engine {engine} does not implement reload_model")


# Prepare one engine runtime before use.
def prepare_runtime(engine: str | None) -> None:
    """Prepare the selected engine runtime before it is used."""

    module = _get_engine_module(engine)
    prepare = getattr(module, "prepare_runtime", None)
    if not callable(prepare):
        return

    try:
        parameter_count = len(inspect.signature(prepare).parameters)
    except (TypeError, ValueError):
        parameter_count = 0

    if parameter_count >= 1:
        prepare(engine)
        return

    prepare()


# Clean up one engine runtime.
def cleanup_runtime(engine: str | None) -> None:
    """Release runtime resources for the selected engine."""

    module = _get_engine_module(engine)
    cleanup = getattr(module, "cleanup_runtime", None)
    if callable(cleanup):
        cleanup()


# Prepare every enabled engine runtime.
def prepare_enabled_runtimes() -> None:
    """Start or warm up each engine that is enabled in settings."""

    for engine_id in settings.get_enabled_engine_ids():
        try:
            prepare_runtime(engine_id)
        except Exception as exc:
            logger.warning("Failed to prepare enabled engine %s: %s", engine_id, exc)


# Release runtimes for engines that are no longer enabled.
def cleanup_disabled_runtimes() -> None:
    """Stop managed runtimes for engines that were disabled in settings."""

    enabled_engine_ids = set(settings.get_enabled_engine_ids())
    for engine_id in settings.ENGINE_IDS:
        if engine_id in enabled_engine_ids:
            continue
        try:
            cleanup_runtime(engine_id)
        except Exception as exc:
            logger.warning("Failed to clean up disabled engine %s: %s", engine_id, exc)


# Align managed runtimes with the current enabled-engine flags.
def sync_enabled_engine_runtimes() -> None:
    """Prepare all enabled engines and release resources for disabled ones."""

    prepare_enabled_runtimes()
    cleanup_disabled_runtimes()


# Switch runtime ownership between engines.
def handle_engine_transition(previous_engine: str | None, next_engine: str | None) -> None:
    """Keep enabled engine runtimes in sync when settings change."""

    del previous_engine, next_engine
    try:
        sync_enabled_engine_runtimes()
    except Exception as exc:
        logger.warning("Failed to sync enabled engine runtimes: %s", exc)
