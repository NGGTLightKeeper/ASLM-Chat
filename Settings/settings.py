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
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
SETTINGS_FILE = BASE_DIR / "Settings" / "settings.json"

ENGINE_LABELS = {
    "ollama-service": "Ollama",
    "lms": "LM Studio",
    "openai": "OpenAI-Compatible",
}

ENGINE_ALIASES = {
    "ollama": "ollama-service",
    "ollama-service": "ollama-service",
    "lms": "lms",
    "lm-studio": "lms",
    "openai": "openai",
    "openai-api": "openai",
}

ENGINE_URL_KEYS = {
    "ollama-service": None,
    "lms": "lms_url",
    "openai": "openai_url",
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
    "lms": False,
    "lms_url": "127.0.0.1:1234",
    "openai": False,
    "openai_url": "127.0.0.1:8000/v1",
    "openai_api_key": "",
}

NORMALIZED_ADDRESS_KEYS = {"lms_url", "openai_url"}


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


def normalize_engine_address(value: Any) -> str:
    """Normalize engine endpoint values to a scheme-free storage format."""
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""

    parsed = urlparse(raw_value)
    if parsed.scheme and parsed.netloc:
        normalized = f"{parsed.netloc}{parsed.path}".rstrip("/")
        return normalized

    if parsed.scheme and parsed.path:
        return parsed.path.rstrip("/")

    return raw_value.rstrip("/")


def normalize_engine_name(engine: str | None) -> str:
    """Return the canonical engine identifier used by the project."""
    if not engine:
        return ENGINE_ALIASES["ollama-service"]

    normalized = str(engine).strip().lower()
    return ENGINE_ALIASES.get(normalized, normalized)


def get_supported_engines() -> list[dict[str, str]]:
    """Return the engines that ASLM-Chat can expose in the UI."""
    return [
        {"id": engine_id, "label": ENGINE_LABELS[engine_id]}
        for engine_id in ("ollama-service", "lms", "openai")
    ]


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

    for key in NORMALIZED_ADDRESS_KEYS:
        settings[key] = normalize_engine_address(settings.get(key, DEFAULTS.get(key, "")))

    settings["llm-engine"] = normalize_engine_name(settings.get("llm-engine"))
    return settings


def save_settings(data: dict[str, Any]) -> None:
    """Persist the given settings dictionary to ``settings.json``."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def _to_env_var_name(key: str) -> str:
    """Map an internal settings key to the ASLM runtime environment format."""
    return f"ASLM_{key.replace('-', '_').upper()}"


def _serialize_env_value(value: Any) -> str:
    """Serialize Python values into environment-friendly strings."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _get_module_manifest_path() -> Path | None:
    """Return the module manifest path if the module is running under ASLM."""
    module_dir = os.environ.get("ASLM_MODULE_DIR", "").strip()
    if module_dir:
        manifest_path = Path(module_dir) / "ASLM_Module.json"
        if manifest_path.exists():
            return manifest_path

    manifest_path = BASE_DIR / "ASLM_Module.json"
    return manifest_path if manifest_path.exists() else None


def _sync_module_manifest_setting(key: str, value: Any) -> None:
    """Persist updated runtime settings back into the module manifest."""
    manifest_path = _get_module_manifest_path()
    if manifest_path is None:
        return

    try:
        with manifest_path.open("r", encoding="utf-8") as file:
            manifest = json.load(file)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read %s: %s", manifest_path, exc)
        return

    settings_list = manifest.get("settings")
    if not isinstance(settings_list, list):
        return

    changed = False
    for setting_item in settings_list:
        if not isinstance(setting_item, dict):
            continue
        if setting_item.get("key") != key:
            continue

        setting_item["value"] = value
        changed = True
        break

    if not changed:
        return

    try:
        with manifest_path.open("w", encoding="utf-8") as file:
            json.dump(manifest, file, indent=4, ensure_ascii=False)
            file.write("\n")
    except OSError as exc:
        logger.warning("Could not write %s: %s", manifest_path, exc)


def get(key: str, default: Any = None) -> Any:
    """Return a single setting value by key."""
    return load_settings().get(key, default)


def set(key: str, value: Any) -> None:
    """Update a single setting value and save the full settings file."""
    if key in NORMALIZED_ADDRESS_KEYS:
        value = normalize_engine_address(value)

    data = load_settings()
    data[key] = value
    save_settings(data)

    env_key = _to_env_var_name(key)
    serialized = _serialize_env_value(value)
    if serialized:
        os.environ[env_key] = serialized
    elif env_key in os.environ:
        del os.environ[env_key]

    _sync_module_manifest_setting(key, value)


def get_llm_engine(default: str = "ollama-service") -> str:
    """Return the configured active LLM engine."""
    configured = get("llm-engine", default)
    return normalize_engine_name(configured)


def get_engine_url_key(engine: str | None) -> str | None:
    """Return the settings key that stores the engine endpoint address."""
    canonical = normalize_engine_name(engine)
    return ENGINE_URL_KEYS.get(canonical)


def _infer_openai_scheme(value: str) -> str:
    """Choose a default scheme for OpenAI-compatible endpoints without one."""
    endpoint = str(value or "").strip()
    if not endpoint:
        return "http"

    host_part = endpoint.split("/", 1)[0].strip()
    host_name = host_part.split(":", 1)[0].strip().lower()
    if host_name in {"localhost", "127.0.0.1", "::1"}:
        return "http"

    return "https"


def get_engine_url(engine: str | None) -> str:
    """Return the configured endpoint address for the selected engine."""
    canonical = normalize_engine_name(engine)

    if canonical == "ollama-service":
        port = int(get("ollama-service_port", DEFAULTS["ollama-service_port"]))
        return f"http://127.0.0.1:{port}"

    url_key = get_engine_url_key(canonical)
    if not url_key:
        return ""

    value = normalize_engine_address(get(url_key, DEFAULTS.get(url_key, "")) or "")
    if canonical == "openai" and value and "://" not in value:
        return f"{_infer_openai_scheme(value)}://{value}"
    return value


def get_openai_api_key() -> str:
    """Return the configured API key for OpenAI-compatible clients."""
    configured = get("openai_api_key", "") or os.environ.get("OPENAI_API_KEY", "")
    return str(configured).strip()


def get_runtime_engine_settings() -> dict[str, Any]:
    """Return the UI-facing runtime engine settings snapshot without secrets."""
    openai_api_key = get_openai_api_key()
    active_engine = get_llm_engine()
    return {
        "llm-engine": active_engine,
        "lms_url": normalize_engine_address(get("lms_url", DEFAULTS["lms_url"])),
        "openai_url": normalize_engine_address(get("openai_url", DEFAULTS["openai_url"])),
        "has_openai_api_key": bool(openai_api_key),
        "engine_urls": {
            "ollama-service": get_engine_url("ollama-service"),
            "lms": get_engine_url("lms"),
            "openai": get_engine_url("openai"),
        },
    }


def is_engine_enabled(engine: str | None) -> bool:
    """Return whether the canonical engine is currently enabled."""
    canonical = normalize_engine_name(engine)
    return bool(get(canonical, False))


def is_ollama_engine(engine: str | None) -> bool:
    """Return whether the engine should use the Ollama adapter/service path."""
    return normalize_engine_name(engine) == "ollama-service"
