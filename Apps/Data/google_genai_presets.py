# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.db import IntegrityError, transaction

from Apps.Data.models import GoogleGenAiPreset

DEFAULT_GOOGLE_GENAI_PRESET_NAME = "Default"
DEFAULT_GOOGLE_GENAI_PRESET_CONFIG: dict[str, Any] = {}


# Normalize preset payload values.
# Remove empty nested values while preserving scalar types.
def _normalize_config_value(value: Any) -> Any:
    """Remove empty values while preserving scalar types."""

    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            normalized_child = _normalize_config_value(child)
            if normalized_child in ({}, [], "", None):
                continue

            normalized[str(key)] = normalized_child
        return normalized

    if isinstance(value, list):
        normalized_list = [_normalize_config_value(child) for child in value]
        return [child for child in normalized_list if child not in ("", None, {}, [])]

    return value


# Keep the stored payload compact and predictable.
def normalize_google_genai_preset_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact Google GenAI preset config ready for storage."""

    if not isinstance(config, dict):
        return {}

    normalized = _normalize_config_value(deepcopy(config))
    return normalized if isinstance(normalized, dict) else {}


# Resolve preset records.
# Pick the next available custom preset name.
def _next_custom_preset_name(model_name: str) -> str:
    """Generate the next free custom preset name for a model."""

    existing_names = set(
        GoogleGenAiPreset.objects.filter(model_name=model_name).values_list("name", flat=True)
    )
    index = 1

    while True:
        candidate = f"Custom {index}"
        if candidate not in existing_names:
            return candidate

        index += 1


# Convert a preset model into API payload data.
def _serialize_preset(preset: GoogleGenAiPreset) -> dict[str, Any]:
    """Convert a preset model into the frontend JSON shape."""

    return {
        "id": str(preset.id),
        "model_name": preset.model_name,
        "name": preset.name,
        "config": normalize_google_genai_preset_config(preset.config or {}),
        "is_default": preset.is_default,
        "is_active": preset.is_active,
    }


# Find one preset in a loaded collection.
def _get_preset_by_id(presets: list[GoogleGenAiPreset], preset_id: str) -> GoogleGenAiPreset:
    """Return one preset from a loaded list or raise when it is missing."""

    preset = next((item for item in presets if str(item.id) == str(preset_id)), None)
    if preset is None:
        raise GoogleGenAiPreset.DoesNotExist("Preset not found")

    return preset


# Maintain preset state.
# Ensure one default preset and one active preset exist for a model.
@transaction.atomic
def ensure_google_genai_preset_state(model_name: str) -> tuple[list[GoogleGenAiPreset], GoogleGenAiPreset]:
    """Ensure a model has one default preset and one active preset."""

    normalized_model = str(model_name or "").strip()
    if not normalized_model:
        raise ValueError("Model name is required for Google GenAI presets")

    presets = list(
        GoogleGenAiPreset.objects.select_for_update()
        .filter(model_name=normalized_model)
        .order_by("-is_active", "-is_default", "name")
    )

    # Seed the first default preset when the model has no saved state yet.
    if not presets:
        default_preset = GoogleGenAiPreset.objects.create(
            model_name=normalized_model,
            name=DEFAULT_GOOGLE_GENAI_PRESET_NAME,
            config=deepcopy(DEFAULT_GOOGLE_GENAI_PRESET_CONFIG),
            is_default=True,
            is_active=True,
        )
        return [default_preset], default_preset

    # Recover a missing active preset by promoting the default or first record.
    active_preset = next((preset for preset in presets if preset.is_active), None)
    if active_preset is None:
        active_preset = next((preset for preset in presets if preset.is_default), presets[0])
        active_preset.is_active = True
        active_preset.save(update_fields=["is_active"])

    # Keep only one active preset to avoid UI and runtime drift.
    if sum(1 for preset in presets if preset.is_active) > 1:
        for preset in presets:
            if preset.pk == active_preset.pk or not preset.is_active:
                continue

            preset.is_active = False
            preset.save(update_fields=["is_active"])

    presets = list(
        GoogleGenAiPreset.objects.filter(model_name=normalized_model)
        .order_by("-is_active", "-is_default", "name")
    )
    return presets, active_preset


# Return the preset payload for one model.
def get_google_genai_preset_payload(model_name: str) -> dict[str, Any]:
    """Return presets and the active config for the selected model."""

    presets, active_preset = ensure_google_genai_preset_state(model_name)
    return {
        "model": model_name,
        "active_preset_id": str(active_preset.id),
        "presets": [_serialize_preset(preset) for preset in presets],
        "active_config": normalize_google_genai_preset_config(active_preset.config or {}),
    }


# Mark one preset as active.
@transaction.atomic
def activate_google_genai_preset(model_name: str, preset_id: str) -> dict[str, Any]:
    """Mark one preset as active for its model."""

    presets, _active_preset = ensure_google_genai_preset_state(model_name)
    preset = _get_preset_by_id(presets, preset_id)

    GoogleGenAiPreset.objects.filter(model_name=model_name, is_active=True).exclude(pk=preset.pk).update(
        is_active=False
    )

    if not preset.is_active:
        preset.is_active = True
        preset.save(update_fields=["is_active"])

    return get_google_genai_preset_payload(model_name)


# Create a new custom preset.
@transaction.atomic
def create_google_genai_preset(
    model_name: str,
    *,
    name: str | None = None,
    config: dict[str, Any] | None = None,
    activate: bool = True,
) -> dict[str, Any]:
    """Create a custom preset for the selected model."""

    normalized_model = str(model_name or "").strip()
    if not normalized_model:
        raise ValueError("Model name is required for Google GenAI presets")

    base_name = str(name or "").strip() or _next_custom_preset_name(normalized_model)

    # Start custom presets from normalized input or the built-in baseline.
    try:
        preset = GoogleGenAiPreset.objects.create(
            model_name=normalized_model,
            name=base_name,
            config=normalize_google_genai_preset_config(config) or deepcopy(DEFAULT_GOOGLE_GENAI_PRESET_CONFIG),
            is_default=False,
            is_active=False,
        )
    except IntegrityError as exc:
        raise ValueError(f"A preset named '{base_name}' already exists for {normalized_model}.") from exc

    if activate:
        return activate_google_genai_preset(normalized_model, str(preset.id))

    return get_google_genai_preset_payload(normalized_model)


# Rename a custom preset.
@transaction.atomic
def rename_google_genai_preset(model_name: str, preset_id: str, new_name: str) -> dict[str, Any]:
    """Rename a custom preset without changing its config."""

    normalized_name = str(new_name or "").strip()
    if not normalized_name:
        raise ValueError("Preset name cannot be empty")

    presets, _active_preset = ensure_google_genai_preset_state(model_name)
    preset = _get_preset_by_id(presets, preset_id)
    if preset.is_default:
        raise ValueError("The default preset cannot be renamed")

    preset.name = normalized_name
    try:
        preset.save(update_fields=["name", "updated_at"])
    except IntegrityError as exc:
        raise ValueError(f"A preset named '{normalized_name}' already exists for {model_name}.") from exc

    return get_google_genai_preset_payload(model_name)


# Delete a custom preset.
@transaction.atomic
def delete_google_genai_preset(model_name: str, preset_id: str) -> dict[str, Any]:
    """Delete a custom preset and restore the default when needed."""

    presets, _active_preset = ensure_google_genai_preset_state(model_name)
    preset = _get_preset_by_id(presets, preset_id)
    if preset.is_default:
        raise ValueError("The default preset cannot be deleted")

    was_active = preset.is_active
    preset.delete()

    payload = get_google_genai_preset_payload(model_name)
    if not was_active:
        return payload

    default_preset = next(item for item in payload["presets"] if item.get("is_default"))
    return activate_google_genai_preset(model_name, default_preset["id"])


# Persist changes into the active preset.
@transaction.atomic
def sync_active_google_genai_preset(model_name: str, config: dict[str, Any]) -> dict[str, Any]:
    """Persist UI changes into the active preset."""

    normalized_model = str(model_name or "").strip()
    normalized_config = normalize_google_genai_preset_config(config)
    presets, active_preset = ensure_google_genai_preset_state(normalized_model)

    # Editing the default preset should create a custom active copy.
    if active_preset.is_default:
        if normalize_google_genai_preset_config(active_preset.config) == normalized_config:
            return get_google_genai_preset_payload(normalized_model)

        return create_google_genai_preset(
            normalized_model,
            config=normalized_config,
            activate=True,
        )

    # Custom active presets can be updated in place.
    active_preset.config = normalized_config
    active_preset.save(update_fields=["config", "updated_at"])
    return get_google_genai_preset_payload(normalized_model)
