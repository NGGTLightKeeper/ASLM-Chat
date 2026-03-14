"""Ollama adapter used by the generic LLM registry."""

from __future__ import annotations

import logging
from typing import Any

import ollama

from Settings import settings

logger = logging.getLogger(__name__)


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


def generate(model_name: str, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
    """Generate a chat response through Ollama."""
    client = get_client()
    try:
        think = kwargs.pop("think", None)
        think_level = kwargs.pop("think_level", None)
        call_kwargs = {key: value for key, value in kwargs.items() if key not in {"system", "prompt"}}

        if think is not None:
            call_kwargs["think"] = think

        if think_level is not None:
            options = call_kwargs.setdefault("options", {})
            if isinstance(options, dict):
                options["think_level"] = think_level

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
