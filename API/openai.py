"""OpenAI-compatible adapter backed by the official ``openai`` SDK."""

from __future__ import annotations

import logging
from typing import Any

from Settings import settings

logger = logging.getLogger(__name__)

DIRECT_OPTION_ALIASES = {
    "num_predict": "max_tokens",
}

DIRECT_OPTION_KEYS = {
    "frequency_penalty",
    "logit_bias",
    "max_completion_tokens",
    "max_tokens",
    "n",
    "presence_penalty",
    "reasoning_effort",
    "response_format",
    "seed",
    "stop",
    "temperature",
    "tool_choice",
    "tools",
    "top_p",
    "user",
    "verbosity",
}


def _get_client():
    """Create an OpenAI-compatible client using the configured base URL."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("The 'openai' package is required for OpenAI-compatible support.") from exc

    api_key = settings.get_openai_api_key() or "not-needed"
    return OpenAI(
        api_key=api_key,
        base_url=settings.get_engine_url("openai"),
    )


def _build_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert generic ASLM chat messages to OpenAI-compatible message payloads."""
    payload: list[dict[str, Any]] = []

    for message in messages:
        role = str(message.get("role", "user")).lower()
        content = message.get("content", "") or ""
        images = message.get("images") or []

        if images:
            content_parts: list[dict[str, Any]] = []
            if content:
                content_parts.append({"type": "text", "text": content})
            for image_base64 in images:
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    }
                )
            payload.append({"role": role, "content": content_parts})
            continue

        payload.append({"role": role, "content": content})

    return payload


def _build_openai_request_options(options: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Split generic generation options into OpenAI kwargs and ``extra_body``."""
    direct_options: dict[str, Any] = {}
    extra_body: dict[str, Any] = {}

    for raw_key, raw_value in (options or {}).items():
        normalized_key = DIRECT_OPTION_ALIASES.get(raw_key, raw_key)
        if normalized_key in DIRECT_OPTION_KEYS:
            direct_options[normalized_key] = raw_value
        else:
            extra_body[raw_key] = raw_value

    think_level = kwargs.get("think_level")
    if think_level and "reasoning_effort" not in direct_options and "reasoning_effort" not in extra_body:
        direct_options["reasoning_effort"] = think_level

    if extra_body:
        merged_extra_body = dict(direct_options.get("extra_body", {}) or {})
        merged_extra_body.update(extra_body)
        direct_options["extra_body"] = merged_extra_body

    return direct_options


def get_models() -> list[Any]:
    """Return models exposed by the configured OpenAI-compatible endpoint."""
    client = _get_client()
    try:
        response = client.models.list()
    except Exception as exc:
        logger.error("[OpenAI API] Error listing models: %s", exc)
        return []

    return list(getattr(response, "data", []) or [])


def download_model(model_name: str, **kwargs: Any) -> Any:
    """OpenAI-compatible APIs expose remote models and do not download locally."""
    raise NotImplementedError("OpenAI-compatible models are remote and cannot be downloaded locally.")


def generate(model_name: str, messages: list[dict[str, Any]], **kwargs: Any):
    """Generate a streamed or non-streamed response through an OpenAI-compatible API."""
    client = _get_client()
    options = dict(kwargs.get("options", {}) or {})
    stream = bool(kwargs.get("stream", False))
    prepared_messages = _build_openai_messages(messages)
    request_options = _build_openai_request_options(
        options,
        think=kwargs.get("think"),
        think_level=kwargs.get("think_level"),
    )

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=prepared_messages,
            stream=stream,
            **request_options,
        )

        if stream:
            for chunk in response:
                for choice in getattr(chunk, "choices", []) or []:
                    delta = getattr(choice, "delta", None)
                    content = getattr(delta, "content", "") if delta else ""
                    if content:
                        yield {"message": {"content": content}}
            return

        for choice in getattr(response, "choices", []) or []:
            message = getattr(choice, "message", None)
            content = getattr(message, "content", "") if message else ""
            if content:
                yield {"message": {"content": content}}
    except Exception as exc:
        logger.error("[OpenAI API] Error generating response from %s: %s", model_name, exc)
        raise


def get_model_settings(model_name: str) -> dict[str, Any]:
    """Return basic metadata for a model exposed by an OpenAI-compatible endpoint."""
    client = _get_client()

    try:
        model = client.models.retrieve(model_name)
    except Exception as exc:
        logger.error("[OpenAI API] Error fetching settings for %s: %s", model_name, exc)
        raise

    raw_model = model.to_dict() if hasattr(model, "to_dict") else {}
    return {
        "model": model_name,
        "context_length": raw_model.get("context_length", raw_model.get("max_context_length", 8192)),
        "defaults": {},
        "supports_thinking": False,
        "supports_think_level": False,
        "supports_vision": False,
        "capabilities": [],
        "raw": raw_model,
    }
