"""LM Studio adapter backed by the official ``lmstudio`` Python SDK."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from Settings import settings

logger = logging.getLogger(__name__)


def _get_sdk():
    """Import the LM Studio SDK lazily so Django can boot without the package."""
    try:
        import lmstudio as lms
    except ImportError as exc:
        raise ImportError("The 'lmstudio' package is required for LM Studio support.") from exc

    return lms


def _get_client():
    """Create a fresh LM Studio client bound to the currently configured address."""
    lms = _get_sdk()
    raw_address = settings.get_engine_url("lms")
    parsed = urlparse(raw_address)

    if parsed.scheme and parsed.netloc:
        api_host = parsed.netloc
    elif parsed.scheme and parsed.path:
        api_host = parsed.path
    else:
        api_host = raw_address.strip().rstrip("/")

    return lms, lms.Client(api_host)


def _build_chat_history(lms, messages: list[dict[str, Any]]):
    """Convert generic chat messages to an LM Studio chat history object."""
    chat = lms.Chat()

    for message in messages:
        role = str(message.get("role", "user")).lower()
        content = message.get("content", "") or ""
        images = message.get("images") or []

        if images:
            raise NotImplementedError("LM Studio image inputs are not implemented yet.")

        if role == "system":
            chat.add_system_prompt(content)
        elif role == "assistant":
            chat.add_assistant_response(content)
        else:
            chat.add_user_message(content)

    return chat


def _coerce_model_name(entry: Any) -> str:
    """Extract a stable model name from SDK responses."""
    for attr in ("model_key", "model", "identifier", "id", "display_name"):
        value = getattr(entry, attr, None)
        if value:
            return str(value)

    get_info = getattr(entry, "get_info", None)
    if callable(get_info):
        try:
            info = get_info()
        except Exception:
            return ""

        if hasattr(info, "to_dict"):
            info = info.to_dict()

        if isinstance(info, dict):
            for key in ("model_key", "modelKey", "display_name", "displayName", "identifier", "id"):
                value = info.get(key)
                if value:
                    return str(value)

    return ""


def get_models() -> list[Any]:
    """Return models visible to the configured LM Studio server."""
    _lms, client = _get_client()
    try:
        downloaded_models = list(client.list_downloaded_models())
    except Exception as exc:
        logger.error("[LM Studio API] Error listing models: %s", exc)
        return []
    finally:
        try:
            client.close()
        except Exception:
            pass

    merged_models: list[Any] = []
    seen_names: set[str] = set()

    for entry in downloaded_models:
        model_name = _coerce_model_name(entry)
        if model_name and model_name not in seen_names:
            seen_names.add(model_name)
            merged_models.append(model_name)

    if merged_models:
        return merged_models

    _lms, client = _get_client()
    try:
        loaded_models = list(client.list_loaded_models())
    except Exception as exc:
        logger.error("[LM Studio API] Error listing loaded models: %s", exc)
        return []
    finally:
        try:
            client.close()
        except Exception:
            pass

    for entry in loaded_models:
        model_name = _coerce_model_name(entry)
        if model_name and model_name not in seen_names:
            seen_names.add(model_name)
            merged_models.append(model_name)

    return merged_models


def download_model(model_name: str, **kwargs: Any) -> Any:
    """LM Studio model downloads are managed by LM Studio itself."""
    raise NotImplementedError("LM Studio model downloads are managed by LM Studio.")


def generate(model_name: str, messages: list[dict[str, Any]], **kwargs: Any):
    """Generate a streamed or non-streamed response through LM Studio."""
    lms, client = _get_client()
    chat = _build_chat_history(lms, messages)
    options = kwargs.get("options", {}) or {}
    stream = bool(kwargs.get("stream", False))

    try:
        model = client.llm.model(model_name)
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
        try:
            client.close()
        except Exception:
            pass


def get_model_settings(model_name: str) -> dict[str, Any]:
    """Return basic capability metadata for an LM Studio model."""
    _lms, client = _get_client()

    try:
        model = client.llm.model(model_name)
        info = model.get_info()
        context_length = model.get_context_length()
    except Exception as exc:
        logger.error("[LM Studio API] Error fetching settings for %s: %s", model_name, exc)
        raise
    finally:
        try:
            client.close()
        except Exception:
            pass

    info_payload = info.to_dict() if hasattr(info, "to_dict") else {}
    capabilities = []

    vision_markers = [
        getattr(info, "vision", None),
        getattr(info, "supports_vision", None),
        info_payload.get("vision"),
        info_payload.get("supports_vision"),
    ]
    if any(bool(marker) for marker in vision_markers):
        capabilities.append("vision")

    return {
        "model": model_name,
        "context_length": int(context_length or 8192),
        "defaults": {},
        "supports_thinking": False,
        "supports_think_level": False,
        "supports_vision": "vision" in capabilities,
        "capabilities": capabilities,
        "raw": info_payload,
    }
