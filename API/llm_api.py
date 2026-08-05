# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import importlib
import inspect
import logging
from types import ModuleType
from typing import Any

from API import mcp as tool_registry
from Settings import settings

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
