"""Adapter registry for LLM engines used by ASLM-Chat."""

from __future__ import annotations

import importlib
import logging
from types import ModuleType
from typing import Any

from Settings import settings

logger = logging.getLogger(__name__)

ENGINE_MODULES = {
    "ollama": "API.ollama",
    "ollama-service": "API.ollama",
    "lms": "API.lms",
    "lm-studio": "API.lms",
    "openai": "API.openai",
    "openai-api": "API.openai",
}


def _get_engine_module(engine: str | None) -> ModuleType:
    """Load the API adapter module for the requested engine."""
    canonical_engine = settings.normalize_engine_name(engine)
    module_name = ENGINE_MODULES.get(canonical_engine)

    if not module_name:
        raise ValueError(f"Unsupported LLM engine: {engine}")

    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        logger.error("Failed to load engine module %s: %s", module_name, exc)
        raise ImportError(f"Failed to load engine module {module_name}: {exc}") from exc


def get_models(engine: str | None) -> Any:
    """Return available models for the selected engine."""
    module = _get_engine_module(engine)
    if hasattr(module, "get_models"):
        return module.get_models()
    raise NotImplementedError(f"Engine {engine} does not implement get_models")


def download_model(engine: str | None, model_name: str, **kwargs: Any) -> Any:
    """Download or pull a model for the selected engine."""
    module = _get_engine_module(engine)
    if hasattr(module, "download_model"):
        return module.download_model(model_name, **kwargs)
    raise NotImplementedError(f"Engine {engine} does not implement download_model")


def generate(engine: str | None, model_name: str, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
    """Generate a response from the selected engine using chat-style messages."""
    module = _get_engine_module(engine)
    if hasattr(module, "generate"):
        return module.generate(model_name, messages, **kwargs)
    raise NotImplementedError(f"Engine {engine} does not implement generate")


def get_model_settings(engine: str | None, model_name: str) -> Any:
    """Return model metadata or settings from the selected engine."""
    module = _get_engine_module(engine)
    if hasattr(module, "get_model_settings"):
        return module.get_model_settings(model_name)
    raise NotImplementedError(f"Engine {engine} does not implement get_model_settings")


def prepare_runtime(engine: str | None) -> None:
    """Prepare the selected engine runtime before it is used."""
    module = _get_engine_module(engine)
    prepare = getattr(module, "prepare_runtime", None)
    if callable(prepare):
        prepare()


def cleanup_runtime(engine: str | None) -> None:
    """Release runtime resources for the selected engine when it is deselected."""
    module = _get_engine_module(engine)
    cleanup = getattr(module, "cleanup_runtime", None)
    if callable(cleanup):
        cleanup()


def handle_engine_transition(previous_engine: str | None, next_engine: str | None) -> None:
    """Apply runtime teardown/startup when the active engine changes."""
    previous = settings.normalize_engine_name(previous_engine)
    current = settings.normalize_engine_name(next_engine)

    if previous == current:
        return

    try:
        cleanup_runtime(previous)
    except Exception as exc:
        logger.warning("Failed to clean up engine %s: %s", previous, exc)

    try:
        prepare_runtime(current)
    except Exception as exc:
        logger.warning("Failed to prepare engine %s: %s", current, exc)


def reload_model(engine: str | None, model_name: str) -> None:
    """Reload a model when the selected engine exposes explicit reload support."""
    module = _get_engine_module(engine)
    reload_func = getattr(module, "reload_model", None)
    if callable(reload_func):
        reload_func(model_name)
