"""Helpers for storing and applying per-model Ollama presets."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.db import IntegrityError, transaction

from Apps.Data.models import OllamaPreset

DEFAULT_OLLAMA_PRESET_NAME = "Default"
DEFAULT_OLLAMA_PRESET_CONFIG: dict[str, Any] = {
    "num_ctx": 32768,
    "num_predict": 8192,
    "think": True,
    "think_level": "medium",
}


def _normalize_config_value(value: Any) -> Any:
    """Remove empty values while keeping the scalar types used by Ollama."""
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


def normalize_ollama_preset_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact preset payload ready for persistence."""
    if not isinstance(config, dict):
        return {}

    normalized = _normalize_config_value(deepcopy(config))
    return normalized if isinstance(normalized, dict) else {}


def _next_custom_preset_name(model_name: str) -> str:
    """Generate a stable preset name for auto-created custom presets."""
    existing_names = set(
        OllamaPreset.objects.filter(model_name=model_name).values_list("name", flat=True)
    )
    index = 1
    while True:
        candidate = f"Custom {index}"
        if candidate not in existing_names:
            return candidate
        index += 1


def _serialize_preset(preset: OllamaPreset) -> dict[str, Any]:
    """Convert a preset model to the JSON shape expected by the frontend."""
    return {
        "id": str(preset.id),
        "model_name": preset.model_name,
        "name": preset.name,
        "config": deepcopy(preset.config or {}),
        "is_default": preset.is_default,
        "is_active": preset.is_active,
    }


@transaction.atomic
def ensure_ollama_preset_state(model_name: str) -> tuple[list[OllamaPreset], OllamaPreset]:
    """Ensure that a model has a default preset and a single active preset."""
    normalized_model = str(model_name or "").strip()
    if not normalized_model:
        raise ValueError("Model name is required for Ollama presets")

    presets = list(
        OllamaPreset.objects.select_for_update()
        .filter(model_name=normalized_model)
        .order_by("-is_active", "-is_default", "name")
    )

    if not presets:
        default_preset = OllamaPreset.objects.create(
            model_name=normalized_model,
            name=DEFAULT_OLLAMA_PRESET_NAME,
            config=deepcopy(DEFAULT_OLLAMA_PRESET_CONFIG),
            is_default=True,
            is_active=True,
        )
        return [default_preset], default_preset

    active_preset = next((preset for preset in presets if preset.is_active), None)
    if active_preset is None:
        active_preset = next((preset for preset in presets if preset.is_default), presets[0])
        active_preset.is_active = True
        active_preset.save(update_fields=["is_active"])

    if sum(1 for preset in presets if preset.is_active) > 1:
        for preset in presets:
            if preset.pk == active_preset.pk:
                continue
            if preset.is_active:
                preset.is_active = False
                preset.save(update_fields=["is_active"])

    presets = list(
        OllamaPreset.objects.filter(model_name=normalized_model)
        .order_by("-is_active", "-is_default", "name")
    )
    return presets, active_preset


def get_ollama_preset_payload(model_name: str) -> dict[str, Any]:
    """Return the preset list and active preset for the selected model."""
    presets, active_preset = ensure_ollama_preset_state(model_name)
    return {
        "model": model_name,
        "active_preset_id": str(active_preset.id),
        "presets": [_serialize_preset(preset) for preset in presets],
        "active_config": deepcopy(active_preset.config or {}),
    }


@transaction.atomic
def activate_ollama_preset(model_name: str, preset_id: str) -> dict[str, Any]:
    """Mark the selected preset as active for its model."""
    presets, _active_preset = ensure_ollama_preset_state(model_name)
    preset = next((item for item in presets if str(item.id) == str(preset_id)), None)
    if preset is None:
        raise OllamaPreset.DoesNotExist("Preset not found")

    OllamaPreset.objects.filter(model_name=model_name, is_active=True).exclude(pk=preset.pk).update(
        is_active=False
    )
    if not preset.is_active:
        preset.is_active = True
        preset.save(update_fields=["is_active"])

    return get_ollama_preset_payload(model_name)


@transaction.atomic
def create_ollama_preset(
    model_name: str,
    *,
    name: str | None = None,
    config: dict[str, Any] | None = None,
    activate: bool = True,
) -> dict[str, Any]:
    """Create an additional preset for the selected Ollama model."""
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


@transaction.atomic
def rename_ollama_preset(model_name: str, preset_id: str, new_name: str) -> dict[str, Any]:
    """Rename a non-default preset while keeping its configuration intact."""
    normalized_name = str(new_name or "").strip()
    if not normalized_name:
        raise ValueError("Preset name cannot be empty")

    presets, _active_preset = ensure_ollama_preset_state(model_name)
    preset = next((item for item in presets if str(item.id) == str(preset_id)), None)
    if preset is None:
        raise OllamaPreset.DoesNotExist("Preset not found")
    if preset.is_default:
        raise ValueError("The default preset cannot be renamed")

    preset.name = normalized_name
    try:
        preset.save(update_fields=["name", "updated_at"])
    except IntegrityError as exc:
        raise ValueError(f"A preset named '{normalized_name}' already exists for {model_name}.") from exc
    return get_ollama_preset_payload(model_name)


@transaction.atomic
def delete_ollama_preset(model_name: str, preset_id: str) -> dict[str, Any]:
    """Delete a custom preset and fall back to the default one when needed."""
    presets, _active_preset = ensure_ollama_preset_state(model_name)
    preset = next((item for item in presets if str(item.id) == str(preset_id)), None)
    if preset is None:
        raise OllamaPreset.DoesNotExist("Preset not found")
    if preset.is_default:
        raise ValueError("The default preset cannot be deleted")

    was_active = preset.is_active
    preset.delete()

    payload = get_ollama_preset_payload(model_name)
    if was_active:
        default_preset = next(
            item for item in payload["presets"] if item.get("is_default")
        )
        return activate_ollama_preset(model_name, default_preset["id"])
    return payload


@transaction.atomic
def sync_active_ollama_preset(model_name: str, config: dict[str, Any]) -> dict[str, Any]:
    """Persist UI changes to the active preset, cloning the default when needed."""
    normalized_model = str(model_name or "").strip()
    normalized_config = normalize_ollama_preset_config(config)
    presets, active_preset = ensure_ollama_preset_state(normalized_model)

    if active_preset.is_default:
        if normalize_ollama_preset_config(active_preset.config) == normalized_config:
            return get_ollama_preset_payload(normalized_model)

        return create_ollama_preset(
            normalized_model,
            config=normalized_config,
            activate=True,
        )

    active_preset.config = normalized_config
    active_preset.save(update_fields=["config", "updated_at"])
    return get_ollama_preset_payload(normalized_model)
