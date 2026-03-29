# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.db import IntegrityError, transaction
from API import ollama as ollama_api
from Apps.Data.models import OllamaPreset

DEFAULT_OLLAMA_PRESET_NAME = "Default"
DEFAULT_OLLAMA_PRESET_CONFIG: dict[str, Any] = {
    "num_ctx": 32768,
    "num_predict": 8192,
    "think": True,
    "think_level": "medium",
}
OLLAMA_PRESET_CONTROL_KEYS = {
    "think",
    "thinking",
    "reasoning",
    "think_level",
    "thinking_level",
    "reasoning_effort",
}


# Clean nested preset values
def _normalize_config_value(value: Any) -> Any:
    """Remove empty values while preserving Ollama scalar types."""

    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            normalized_child = _normalize_config_value(child)
            if normalized_child in ({}, [], "", None):
                continue
            normalized[key] = normalized_child
        return normalized

    if isinstance(value, list):
        normalized_list = [_normalize_config_value(child) for child in value]
        return [child for child in normalized_list if child not in ("", None, {}, [])]

    return value

# Normalize preset payload
def normalize_ollama_preset_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact preset config ready for storage."""

    if not isinstance(config, dict):
        return {}

    normalized = _normalize_config_value(deepcopy(config))
    if not isinstance(normalized, dict):
        return {}

    clean_config: dict[str, Any] = {}
    for key, value in normalized.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        if normalized_key in OLLAMA_PRESET_CONTROL_KEYS:
            clean_config[normalized_key] = value
            continue
        if normalized_key in ollama_api.OLLAMA_TOP_LEVEL_CHAT_KEYS:
            clean_config[normalized_key] = value
            continue
        if ollama_api.is_supported_runtime_option_key(normalized_key):
            clean_config[normalized_key] = value

    return clean_config


# Pick next custom preset name
def _next_custom_preset_name(model_name: str) -> str:
    """Generate the next free custom preset name for a model."""

    existing_names = set(
        OllamaPreset.objects.filter(model_name=model_name).values_list("name", flat=True)
    )
    index = 1

    while True:
        candidate = f"Custom {index}"
        if candidate not in existing_names:
            return candidate
        index += 1

# Serialize preset model
def _serialize_preset(preset: OllamaPreset) -> dict[str, Any]:
    """Convert a preset model into the frontend JSON shape."""

    return {
        "id": str(preset.id),
        "model_name": preset.model_name,
        "name": preset.name,
        "config": normalize_ollama_preset_config(preset.config or {}),
        "is_default": preset.is_default,
        "is_active": preset.is_active,
    }

# Find preset by id
def _get_preset_by_id(presets: list[OllamaPreset], preset_id: str) -> OllamaPreset:
    """Return one preset from a loaded list or raise when it is missing."""

    preset = next((item for item in presets if str(item.id) == str(preset_id)), None)
    if preset is None:
        raise OllamaPreset.DoesNotExist("Preset not found")

    return preset


# Ensure valid preset state
@transaction.atomic
def ensure_ollama_preset_state(model_name: str) -> tuple[list[OllamaPreset], OllamaPreset]:
    """Ensure a model has one default preset and one active preset."""

    normalized_model = str(model_name or "").strip()
    if not normalized_model:
        raise ValueError("Model name is required for Ollama presets")

    presets = list(
        OllamaPreset.objects.select_for_update()
        .filter(model_name=normalized_model)
        .order_by("-is_active", "-is_default", "name")
    )

    # Create the initial default preset when the model has no saved state yet.
    if not presets:
        default_preset = OllamaPreset.objects.create(
            model_name=normalized_model,
            name=DEFAULT_OLLAMA_PRESET_NAME,
            config=deepcopy(DEFAULT_OLLAMA_PRESET_CONFIG),
            is_default=True,
            is_active=True,
        )
        return [default_preset], default_preset

    # Reuse the active preset when present, otherwise fall back to the default
    # preset or the first available record.
    active_preset = next((preset for preset in presets if preset.is_active), None)
    if active_preset is None:
        active_preset = next((preset for preset in presets if preset.is_default), presets[0])
        active_preset.is_active = True
        active_preset.save(update_fields=["is_active"])

    # Keep only one active preset so the UI and runtime stay in sync.
    if sum(1 for preset in presets if preset.is_active) > 1:
        for preset in presets:
            if preset.pk == active_preset.pk or not preset.is_active:
                continue
            preset.is_active = False
            preset.save(update_fields=["is_active"])

    presets = list(
        OllamaPreset.objects.filter(model_name=normalized_model)
        .order_by("-is_active", "-is_default", "name")
    )
    return presets, active_preset

# Read preset payload
def get_ollama_preset_payload(model_name: str) -> dict[str, Any]:
    """Return presets and the active config for the selected model."""

    presets, active_preset = ensure_ollama_preset_state(model_name)
    return {
        "model": model_name,
        "active_preset_id": str(active_preset.id),
        "presets": [_serialize_preset(preset) for preset in presets],
        "active_config": normalize_ollama_preset_config(active_preset.config or {}),
    }

# Activate preset
@transaction.atomic
def activate_ollama_preset(model_name: str, preset_id: str) -> dict[str, Any]:
    """Mark one preset as active for its model."""

    presets, _active_preset = ensure_ollama_preset_state(model_name)
    preset = _get_preset_by_id(presets, preset_id)

    OllamaPreset.objects.filter(model_name=model_name, is_active=True).exclude(pk=preset.pk).update(
        is_active=False
    )
    if not preset.is_active:
        preset.is_active = True
        preset.save(update_fields=["is_active"])

    return get_ollama_preset_payload(model_name)

# Create preset
@transaction.atomic
def create_ollama_preset(
    model_name: str,
    *,
    name: str | None = None,
    config: dict[str, Any] | None = None,
    activate: bool = True,
) -> dict[str, Any]:
    """Create a custom preset for the selected model."""

    normalized_model = str(model_name or "").strip()
    if not normalized_model:
        raise ValueError("Model name is required for Ollama presets")

    base_name = str(name or "").strip() or _next_custom_preset_name(normalized_model)

    try:
        preset = OllamaPreset.objects.create(
            model_name=normalized_model,
            name=base_name,
            config=normalize_ollama_preset_config(config) or deepcopy(DEFAULT_OLLAMA_PRESET_CONFIG),
            is_default=False,
            is_active=False,
        )
    except IntegrityError as exc:
        raise ValueError(f"A preset named '{base_name}' already exists for {normalized_model}.") from exc

    if activate:
        return activate_ollama_preset(normalized_model, str(preset.id))

    return get_ollama_preset_payload(normalized_model)

# Rename preset
@transaction.atomic
def rename_ollama_preset(model_name: str, preset_id: str, new_name: str) -> dict[str, Any]:
    """Rename a custom preset without changing its config."""

    normalized_name = str(new_name or "").strip()
    if not normalized_name:
        raise ValueError("Preset name cannot be empty")

    presets, _active_preset = ensure_ollama_preset_state(model_name)
    preset = _get_preset_by_id(presets, preset_id)
    if preset.is_default:
        raise ValueError("The default preset cannot be renamed")

    preset.name = normalized_name
    try:
        preset.save(update_fields=["name", "updated_at"])
    except IntegrityError as exc:
        raise ValueError(f"A preset named '{normalized_name}' already exists for {model_name}.") from exc

    return get_ollama_preset_payload(model_name)

# Delete preset
@transaction.atomic
def delete_ollama_preset(model_name: str, preset_id: str) -> dict[str, Any]:
    """Delete a custom preset and restore the default when needed."""

    presets, _active_preset = ensure_ollama_preset_state(model_name)
    preset = _get_preset_by_id(presets, preset_id)
    if preset.is_default:
        raise ValueError("The default preset cannot be deleted")

    was_active = preset.is_active
    preset.delete()

    payload = get_ollama_preset_payload(model_name)
    if not was_active:
        return payload

    default_preset = next(item for item in payload["presets"] if item.get("is_default"))
    return activate_ollama_preset(model_name, default_preset["id"])

# Sync active preset
@transaction.atomic
def sync_active_ollama_preset(model_name: str, config: dict[str, Any]) -> dict[str, Any]:
    """Persist UI changes into the active preset."""

    normalized_model = str(model_name or "").strip()
    normalized_config = normalize_ollama_preset_config(config)
    presets, active_preset = ensure_ollama_preset_state(normalized_model)

    # Editing the default preset creates a new active custom preset so the
    # original baseline remains available.
    if active_preset.is_default:
        if normalize_ollama_preset_config(active_preset.config) == normalized_config:
            return get_ollama_preset_payload(normalized_model)

        return create_ollama_preset(
            normalized_model,
            config=normalized_config,
            activate=True,
        )

    # Custom active presets can be updated in place.
    active_preset.config = normalized_config
    active_preset.save(update_fields=["config", "updated_at"])
    return get_ollama_preset_payload(normalized_model)
