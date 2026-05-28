# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import json
import logging
import os
import threading
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
    "google-genai": "Google GenAI",
}

ENGINE_IDS = ("ollama-service", "lms", "openai", "google-genai")

ENGINE_ALIASES = {
    "ollama": "ollama-service",
    "ollama-service": "ollama-service",
    "lms": "lms",
    "lm-studio": "lms",
    "openai": "openai",
    "openai-api": "openai",
    "google-genai": "google-genai",
    "google_genai": "google-genai",
    "google": "google-genai",
    "gemini": "google-genai",
}

ENGINE_URL_KEYS = {
    "ollama-service": None,
    "lms": "lms_url",
    "openai": "openai_url",
    "google-genai": "google_genai_url",
}

ENGINE_API_KEY_KEYS = {
    "openai": "openai_api_key",
    "google-genai": "google_genai_api_key",
}

DEFAULTS: dict[str, Any] = {
    "ui-port": 20000,
    "api-port": 20001,
    "debug": True,
    "console_log_level": "debug",
    "secret_key": "",
    "allowed_hosts": ["127.0.0.1", "localhost"],
    "llm-engine": "ollama-service",
    "ollama-service_port": 20003,
    "ollama-service": False,
    "ollama-service_path": None,
    "ollama-service_data": None,
    "ollama-service_models": None,
    "lms": False,
    "lms_url": "127.0.0.1:1234",
    "openai": False,
    "openai_url": "127.0.0.1:8000/v1",
    "openai_api_key": "",
    "google-genai": False,
    "google_genai_url": "generativelanguage.googleapis.com",
    "google_genai_api_key": "",
    # False = legacy citation chips (search snippet preview only).
    "citation-alignment-enabled": False,
}

CONSOLE_LOG_LEVELS = {"basic", "debug", "trace"}
NORMALIZED_ADDRESS_KEYS = {"lms_url", "openai_url", "google_genai_url"}
IGNORED_ENV_KEYS = {"ASLM_MODULE_ID", "ASLM_MODULE_DIR"}

_settings_cache_lock = threading.RLock()
_settings_cache: dict[str, Any] | None = None
_settings_cache_mtime_ns: int | None = None


# Return the current settings file mtime.
def _get_settings_mtime_ns() -> int | None:
    """Return the current settings file mtime used for cache invalidation."""

    try:
        return SETTINGS_FILE.stat().st_mtime_ns
    except OSError:
        return None


# Store one effective settings snapshot in memory.
def _store_settings_cache(data: dict[str, Any], mtime_ns: int | None) -> None:
    """Replace the in-memory settings snapshot."""

    global _settings_cache, _settings_cache_mtime_ns

    with _settings_cache_lock:
        _settings_cache = dict(data)
        _settings_cache_mtime_ns = mtime_ns


# Invalidate the in-memory settings snapshot.
def _invalidate_settings_cache() -> None:
    """Clear cached settings so the next read reloads from disk."""

    global _settings_cache, _settings_cache_mtime_ns

    with _settings_cache_lock:
        _settings_cache = None
        _settings_cache_mtime_ns = None


# Normalize one raw settings value.
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

# Normalize one raw settings key.
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

# Normalize one engine address for storage.
def normalize_engine_address(value: Any) -> str:
    """Normalize engine endpoint values to a scheme-free storage format."""

    raw_value = str(value or "").strip()
    if not raw_value:
        return ""

    parsed = urlparse(raw_value)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.netloc}{parsed.path}".rstrip("/")

    if parsed.scheme and parsed.path:
        return parsed.path.rstrip("/")

    return raw_value.rstrip("/")

# Normalize one engine identifier.
def normalize_engine_name(engine: str | None) -> str:
    """Return the canonical engine identifier used by the project."""

    if not engine:
        return ENGINE_ALIASES["ollama-service"]

    normalized = str(engine).strip().lower()
    return ENGINE_ALIASES.get(normalized, normalized)


# List enabled engine identifiers from one settings snapshot.
def _get_enabled_engine_ids_from_settings(settings_data: dict[str, Any]) -> list[str]:
    """Return engine ids that are enabled in the given settings snapshot."""

    return [engine_id for engine_id in ENGINE_IDS if bool(settings_data.get(engine_id, False))]


# Resolve one engine against the enabled engine list.
def _resolve_enabled_engine_from_settings(
    settings_data: dict[str, Any],
    engine: str | None,
    default: str = "ollama-service",
) -> str:
    """Return an enabled engine, falling back to the first enabled engine when needed."""

    canonical = normalize_engine_name(engine or default)
    enabled_engine_ids = _get_enabled_engine_ids_from_settings(settings_data)

    if canonical in enabled_engine_ids:
        return canonical
    if enabled_engine_ids:
        return enabled_engine_ids[0]

    return canonical


# List engines supported by the UI.
def get_supported_engines() -> list[dict[str, str]]:
    """Return the enabled engines that ASLM-Chat can expose in the UI."""

    from Apps.UI.locale_catalog import translate

    return [
        {
            "id": engine_id,
            "label": translate(f"engines.{engine_id}", fallback=ENGINE_LABELS[engine_id]),
        }
        for engine_id in get_enabled_engine_ids()
    ]


# List enabled engine identifiers from the effective settings.
def get_enabled_engine_ids() -> list[str]:
    """Return the canonical engine ids currently allowed by settings."""

    return _get_enabled_engine_ids_from_settings(load_settings())


# Resolve one requested engine against the current enabled engine list.
def resolve_enabled_engine(engine: str | None, default: str = "ollama-service") -> str:
    """Return a canonical engine that is currently allowed by settings."""

    return _resolve_enabled_engine_from_settings(load_settings(), engine, default)


# Read the settings payload from disk.
def _load_settings_from_disk() -> dict[str, Any]:
    """Return the JSON settings payload stored on disk."""

    if not SETTINGS_FILE.exists():
        return {}

    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read %s: %s", SETTINGS_FILE, exc)
        return {}

    return data if isinstance(data, dict) else {}

# Apply environment overrides to one settings snapshot.
def _apply_environment_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Apply ``ASLM_`` environment overrides to a settings dictionary."""

    updated = dict(data)

    for env_key, env_value in os.environ.items():
        if not env_key.startswith("ASLM_") or env_key in IGNORED_ENV_KEYS:
            continue

        setting_key = normalize_setting_key(env_key[5:])
        updated[setting_key] = normalize_setting_value(env_value)

    return updated

# Normalize the loaded settings snapshot.
_PORT_SETTING_KEYS = ("ui-port", "api-port", "ollama-service_port")


def _warn_port_collisions(settings: dict[str, Any]) -> None:
    """Log when two services are configured on the same TCP port."""
    by_port: dict[int, list[str]] = {}
    for key in _PORT_SETTING_KEYS:
        raw = settings.get(key)
        try:
            port = int(raw)
        except (TypeError, ValueError):
            continue
        if port <= 0 or port > 65535:
            continue
        by_port.setdefault(port, []).append(key)
    for port, keys in sorted(by_port.items()):
        if len(keys) > 1:
            logger.warning(
                "Settings port collision on %s: %s — assign unique ports in Settings/settings.json",
                port,
                ", ".join(keys),
            )


def _normalize_loaded_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized settings snapshot ready for use."""

    normalized = dict(data)
    normalized.pop("lms_load_config", None)

    for key in NORMALIZED_ADDRESS_KEYS:
        normalized[key] = normalize_engine_address(normalized.get(key, DEFAULTS.get(key, "")))

    normalized["llm-engine"] = _resolve_enabled_engine_from_settings(
        normalized,
        normalized.get("llm-engine"),
        DEFAULTS["llm-engine"],
    )
    _warn_port_collisions(normalized)
    return normalized


# Load the effective settings snapshot.
def load_settings() -> dict[str, Any]:
    """Load settings from disk and apply runtime environment overrides."""

    mtime_ns = _get_settings_mtime_ns()
    with _settings_cache_lock:
        if _settings_cache is not None and _settings_cache_mtime_ns == mtime_ns:
            return dict(_settings_cache)

    settings_data = dict(DEFAULTS)
    settings_data.update(_load_settings_from_disk())
    settings_data = _apply_environment_overrides(settings_data)
    settings_data = _normalize_loaded_settings(settings_data)
    _store_settings_cache(settings_data, mtime_ns)
    return dict(settings_data)

# Save the settings snapshot to disk.
def save_settings(data: dict[str, Any]) -> None:
    """Persist the given settings dictionary to ``settings.json``."""

    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)
    settings_data = dict(DEFAULTS)
    settings_data.update(data)
    settings_data = _apply_environment_overrides(settings_data)
    _store_settings_cache(_normalize_loaded_settings(settings_data), _get_settings_mtime_ns())


# Build one runtime environment variable name.
def _to_env_var_name(key: str) -> str:
    """Map an internal settings key to the ASLM runtime environment format."""

    return f"ASLM_{key.replace('-', '_').upper()}"

# Serialize one value for environment storage.
def _serialize_env_value(value: Any) -> str:
    """Serialize Python values into environment-friendly strings."""

    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)

    return str(value)

# Apply one runtime setting to the current process environment.
def _apply_process_environment_value(key: str, value: Any) -> None:
    """Keep the current process environment in sync with one setting."""

    env_key = _to_env_var_name(key)
    serialized = _serialize_env_value(value)
    if serialized:
        os.environ[env_key] = serialized
    elif env_key in os.environ:
        del os.environ[env_key]

# Load stored settings without applying ASLM_ environment overrides.
def _load_stored_settings_snapshot() -> dict[str, Any]:
    """Return the persisted settings snapshot normalized with defaults."""

    settings_data = dict(DEFAULTS)
    settings_data.update(_load_settings_from_disk())
    return _normalize_loaded_settings(settings_data)

# Locate the ASLM module manifest when available.
def _get_module_manifest_path() -> Path | None:
    """Return the module manifest path when ASLM module metadata is available."""

    module_dir = os.environ.get("ASLM_MODULE_DIR", "").strip()
    if module_dir:
        manifest_path = Path(module_dir) / "ASLM_Module.json"
        if manifest_path.exists():
            return manifest_path

    manifest_path = BASE_DIR / "ASLM_Module.json"
    return manifest_path if manifest_path.exists() else None

# Mirror one runtime setting into the module manifest.
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

        if setting_item.get("value") == value:
            return

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


# Read one setting value.
def get(key: str, default: Any = None) -> Any:
    """Return a single setting value by key."""

    return load_settings().get(key, default)

# Persist one setting value.
def set(key: str, value: Any) -> None:
    """Update one setting value and persist the full settings file."""

    if key == "llm-engine":
        value = resolve_enabled_engine(str(value) if value is not None else None)

    if key in NORMALIZED_ADDRESS_KEYS:
        value = normalize_engine_address(value)

    stored_raw_data = _load_settings_from_disk()
    stored_data = dict(DEFAULTS)
    stored_data.update(stored_raw_data)
    stored_data = _normalize_loaded_settings(stored_data)
    if key in stored_raw_data and stored_data.get(key, DEFAULTS.get(key)) == value:
        _apply_process_environment_value(key, value)
        _store_settings_cache(_apply_environment_overrides(stored_data), _get_settings_mtime_ns())
        return

    # Save the normalized value to disk first.
    data = load_settings()
    data[key] = value
    save_settings(data)

    # Keep the current process environment in sync with the saved value.
    _apply_process_environment_value(key, value)
    _invalidate_settings_cache()

    # Mirror the updated setting into the ASLM module manifest when available.
    _sync_module_manifest_setting(key, value)


# Read the active LLM engine name.
def get_llm_engine(default: str = "ollama-service") -> str:
    """Return the configured active LLM engine."""

    configured = get("llm-engine", default)
    return normalize_engine_name(configured)

# Resolve the settings key for one engine URL.
def get_engine_url_key(engine: str | None) -> str | None:
    """Return the settings key that stores the engine endpoint address."""

    canonical = normalize_engine_name(engine)
    return ENGINE_URL_KEYS.get(canonical)

# Infer a scheme for remote endpoints without one.
def _infer_remote_scheme(value: str) -> str:
    """Choose a sensible scheme for remote API endpoints without one."""

    endpoint = str(value or "").strip()
    if not endpoint:
        return "http"

    host_part = endpoint.split("/", 1)[0].strip()
    host_name = host_part.split(":", 1)[0].strip().lower()
    if host_name in {"localhost", "127.0.0.1", "::1"}:
        return "http"

    return "https"

# Build the effective engine URL.
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
    if canonical in {"openai", "google-genai"} and value and "://" not in value:
        return f"{_infer_remote_scheme(value)}://{value}"

    return value

# Read the OpenAI-compatible API key.
def get_openai_api_key() -> str:
    """Return the configured API key for OpenAI-compatible clients."""

    configured = get("openai_api_key", "") or os.environ.get("OPENAI_API_KEY", "")
    return str(configured).strip()

# Read the Google GenAI API key.
def get_google_genai_api_key() -> str:
    """Return the configured API key for Google GenAI clients."""

    configured = (
        get("google_genai_api_key", "")
        or os.environ.get("GOOGLE_API_KEY", "")
        or os.environ.get("GEMINI_API_KEY", "")
    )
    return str(configured).strip()

# Resolve the settings key for one engine API key.
def get_engine_api_key_key(engine: str | None) -> str | None:
    """Return the settings key that stores the engine API key."""

    canonical = normalize_engine_name(engine)
    return ENGINE_API_KEY_KEYS.get(canonical)

# Read the configured API key for one engine.
def get_engine_api_key(engine: str | None) -> str:
    """Return the configured API key for one engine when supported."""

    canonical = normalize_engine_name(engine)
    if canonical == "openai":
        return get_openai_api_key()
    if canonical == "google-genai":
        return get_google_genai_api_key()
    return ""

# Build the runtime settings payload for the UI.
def get_runtime_engine_settings() -> dict[str, Any]:
    """Return the UI-facing runtime engine settings snapshot without secrets."""

    openai_api_key = get_openai_api_key()
    google_genai_api_key = get_google_genai_api_key()
    active_engine = get_llm_engine()
    engine_api_keys = {
        "ollama-service": False,
        "lms": False,
        "openai": bool(openai_api_key),
        "google-genai": bool(google_genai_api_key),
    }

    return {
        "llm-engine": active_engine,
        "console_log_level": get_console_log_level(),
        "lms_url": normalize_engine_address(get("lms_url", DEFAULTS["lms_url"])),
        "openai_url": normalize_engine_address(get("openai_url", DEFAULTS["openai_url"])),
        "google_genai_url": normalize_engine_address(get("google_genai_url", DEFAULTS["google_genai_url"])),
        "has_openai_api_key": bool(openai_api_key),
        "has_google_genai_api_key": bool(google_genai_api_key),
        "active_has_api_key": bool(engine_api_keys.get(active_engine, False)),
        "engine_api_keys": engine_api_keys,
        "engine_api_key_keys": dict(ENGINE_API_KEY_KEYS),
        "engine_urls": {
            "ollama-service": get_engine_url("ollama-service"),
            "lms": get_engine_url("lms"),
            "openai": get_engine_url("openai"),
            "google-genai": get_engine_url("google-genai"),
        },
    }


# Read the console log level.
def get_console_log_level(default: str = "debug") -> str:
    """Return the normalized console log detail level."""

    configured = str(get("console_log_level", default) or default).strip().lower()
    return configured if configured in CONSOLE_LOG_LEVELS else default

# Check whether debug console output is enabled.
def is_console_debug_enabled() -> bool:
    """Return whether debug-or-higher console events should be emitted."""

    return get_console_log_level() in {"debug", "trace"}

# Check whether trace console output is enabled.
def is_console_trace_enabled() -> bool:
    """Return whether the highest-detail console tracing is enabled."""

    return get_console_log_level() == "trace"


# Check whether one engine is enabled.
def is_engine_enabled(engine: str | None) -> bool:
    """Return whether the canonical engine is currently enabled."""

    canonical = normalize_engine_name(engine)
    return bool(get(canonical, False))

# Check whether the engine uses the Ollama adapter path.
def is_ollama_engine(engine: str | None) -> bool:
    """Return whether the engine should use the Ollama adapter path."""

    return normalize_engine_name(engine) == "ollama-service"
