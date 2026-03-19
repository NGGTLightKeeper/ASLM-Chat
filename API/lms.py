# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from Settings import settings

logger = logging.getLogger(__name__)


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


# Build chat history
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
    """Generate a streamed or non-streamed response through LM Studio."""

    lms, client = _get_client()
    chat = _build_chat_history(lms, messages)
    options = kwargs.get("options", {}) or {}
    stream = bool(kwargs.get("stream", False))

    try:
        model = _get_model_handle(client, model_name)

        # The SDK uses separate methods for stream and full response modes.
        if stream:
            for fragment in model.respond_stream(chat, config=options or None):
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
    capabilities: list[str] = []

    return {
        "model": model_name,
        "context_length": 8192,
        "defaults": {},
        "supports_thinking": False,
        "supports_think_level": False,
        "supports_vision": False,
        "capabilities": capabilities,
        "raw": info_payload,
    }
