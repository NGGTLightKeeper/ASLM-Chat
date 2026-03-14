"""Settings helpers for ASLM-Chat.

This module owns the lightweight JSON settings file used by the ASLM module
runtime. It also merges environment overrides injected by ASLM at process
startup, so the Django project can run without editing files on disk.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
SETTINGS_FILE = BASE_DIR / "Settings" / "settings.json"

ENGINE_ALIASES = {
    "ollama": "ollama-service",
    "ollama-service": "ollama-service",
    "lms": "lms",
    "lm-studio": "lms",
    "openai": "openai",
    "openai-api": "openai",
}

# Default values used when a key is missing from settings.json.
DEFAULTS: dict[str, Any] = {
    "ui-port": 30000,
    "api-port": 30001,
    "debug": True,
    "secret_key": "",
    "allowed_hosts": ["127.0.0.1", "localhost"],
    "llm-engine": "ollama-service",
    "ollama-service_port": 30002,
    "ollama-service": False,
    "ollama-service_path": None,
    "ollama-service_data": None,
    "ollama-service_models": None,
}


def normalize_setting_value(value: Any) -> Any:
    """Convert serialized or environment-provided values to Python scalars."""
    if not isinstance(value, str):
        return value

    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"none", "null"}:
        return None

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        pass

    if value.startswith(("{", "[")):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    return value


def normalize_setting_key(raw_key: str) -> str:
    """Map environment-style keys to the internal settings schema."""
    key = raw_key.strip().lower()
    if key in DEFAULTS:
        return key

    dashed = key.replace("_", "-")
    if dashed in DEFAULTS:
        return dashed

    underscored = key.replace("-", "_")
    if underscored in DEFAULTS:
        return underscored

    return key


def normalize_engine_name(engine: str | None) -> str:
    """Return the canonical engine identifier used by the project."""
    if not engine:
        return ENGINE_ALIASES["ollama-service"]

    normalized = str(engine).strip().lower()
    return ENGINE_ALIASES.get(normalized, normalized)


def load_settings() -> dict[str, Any]:
    """Load settings from disk and apply runtime environment overrides."""
    settings = dict(DEFAULTS)

    if SETTINGS_FILE.exists():
        try:
            with SETTINGS_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s: %s", SETTINGS_FILE, exc)
        else:
            if isinstance(data, dict):
                settings.update(data)

    for env_key, env_value in os.environ.items():
        if not env_key.startswith("ASLM_") or env_key in {"ASLM_MODULE_ID", "ASLM_MODULE_DIR"}:
            continue

        setting_key = normalize_setting_key(env_key[5:])
        settings[setting_key] = normalize_setting_value(env_value)

    settings["llm-engine"] = normalize_engine_name(settings.get("llm-engine"))
    return settings


def save_settings(data: dict[str, Any]) -> None:
    """Persist the given settings dictionary to ``settings.json``."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def get(key: str, default: Any = None) -> Any:
    """Return a single setting value by key."""
    return load_settings().get(key, default)


def set(key: str, value: Any) -> None:
    """Update a single setting value and save the full settings file."""
    data = load_settings()
    data[key] = value
    save_settings(data)


def get_llm_engine(default: str = "ollama-service") -> str:
    """Return the configured active LLM engine."""
    configured = get("llm-engine", default)
    return normalize_engine_name(configured)


def is_engine_enabled(engine: str | None) -> bool:
    """Return whether the canonical engine is currently enabled."""
    canonical = normalize_engine_name(engine)
    return bool(get(canonical, False))


def is_ollama_engine(engine: str | None) -> bool:
    """Return whether the engine should use the Ollama adapter/service path."""
    return normalize_engine_name(engine) == "ollama-service"
