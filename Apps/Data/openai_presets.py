# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.db import IntegrityError, transaction

from Apps.Data.models import OpenAiPreset

DEFAULT_OPENAI_PRESET_NAME = "Default"
DEFAULT_OPENAI_PRESET_CONFIG: dict[str, Any] = {}


# Normalize the endpoint URL used to scope presets.
def normalize_openai_endpoint_url(endpoint_url: str | None) -> str:
    """Return a stable endpoint key so the same URL always maps to one scope."""

    return str(endpoint_url or "").strip().rstrip("/")


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
def normalize_openai_preset_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact OpenAI preset config ready for storage."""

    if not isinstance(config, dict):
        return {}

    normalized = _normalize_config_value(deepcopy(config))
    return normalized if isinstance(normalized, dict) else {}


# Resolve preset records.
# Pick the next available custom preset name.
def _next_custom_preset_name(endpoint_url: str, model_name: str) -> str:
    """Generate the next free custom preset name for an endpoint and model."""

    existing_names = set(
        OpenAiPreset.objects.filter(endpoint_url=endpoint_url, model_name=model_name).values_list(
            "name", flat=True
        )
    )
    index = 1

    while True:
        candidate = f"Custom {index}"
        if candidate not in existing_names:
            return candidate

        index += 1


# Convert a preset model into API payload data.
def _serialize_preset(preset: OpenAiPreset) -> dict[str, Any]:
    """Convert a preset model into the frontend JSON shape."""

    return {
        "id": str(preset.id),
        "endpoint_url": preset.endpoint_url,
        "model_name": preset.model_name,
        "name": preset.name,
        "config": normalize_openai_preset_config(preset.config or {}),
        "is_default": preset.is_default,
        "is_active": preset.is_active,
    }


# Find one preset in a loaded collection.
def _get_preset_by_id(presets: list[OpenAiPreset], preset_id: str) -> OpenAiPreset:
    """Return one preset from a loaded list or raise when it is missing."""

    preset = next((item for item in presets if str(item.id) == str(preset_id)), None)
    if preset is None:
        raise OpenAiPreset.DoesNotExist("Preset not found")

    return preset


# Maintain preset state.
# Ensure one default preset and one active preset exist for an endpoint and model.
@transaction.atomic
def ensure_openai_preset_state(endpoint_url: str, model_name: str) -> tuple[list[OpenAiPreset], OpenAiPreset]:
    """Ensure an endpoint/model pair has one default preset and one active preset."""

    normalized_endpoint = normalize_openai_endpoint_url(endpoint_url)
    normalized_model = str(model_name or "").strip()
    if not normalized_model:
        raise ValueError("Model name is required for OpenAI presets")

    presets = list(
        OpenAiPreset.objects.select_for_update()
        .filter(endpoint_url=normalized_endpoint, model_name=normalized_model)
        .order_by("-is_active", "-is_default", "name")
    )

    # Seed the first default preset when this endpoint/model has no state yet.
    if not presets:
        default_preset = OpenAiPreset.objects.create(
            endpoint_url=normalized_endpoint,
            model_name=normalized_model,
            name=DEFAULT_OPENAI_PRESET_NAME,
            config=deepcopy(DEFAULT_OPENAI_PRESET_CONFIG),
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
        OpenAiPreset.objects.filter(endpoint_url=normalized_endpoint, model_name=normalized_model)
        .order_by("-is_active", "-is_default", "name")
    )
    return presets, active_preset


# Return the preset payload for one endpoint and model.
def get_openai_preset_payload(endpoint_url: str, model_name: str) -> dict[str, Any]:
    """Return presets and the active config for the selected endpoint and model."""

    presets, active_preset = ensure_openai_preset_state(endpoint_url, model_name)
    return {
        "endpoint_url": normalize_openai_endpoint_url(endpoint_url),
        "model": model_name,
        "active_preset_id": str(active_preset.id),
        "presets": [_serialize_preset(preset) for preset in presets],
        "active_config": normalize_openai_preset_config(active_preset.config or {}),
    }


# Mark one preset as active.
@transaction.atomic
def activate_openai_preset(endpoint_url: str, model_name: str, preset_id: str) -> dict[str, Any]:
    """Mark one preset as active for its endpoint and model."""

    normalized_endpoint = normalize_openai_endpoint_url(endpoint_url)
    presets, _active_preset = ensure_openai_preset_state(normalized_endpoint, model_name)
    preset = _get_preset_by_id(presets, preset_id)

    OpenAiPreset.objects.filter(
        endpoint_url=normalized_endpoint, model_name=model_name, is_active=True
    ).exclude(pk=preset.pk).update(is_active=False)

    if not preset.is_active:
        preset.is_active = True
        preset.save(update_fields=["is_active"])

    return get_openai_preset_payload(normalized_endpoint, model_name)


# Create a new custom preset.
@transaction.atomic
def create_openai_preset(
    endpoint_url: str,
    model_name: str,
    *,
    name: str | None = None,
    config: dict[str, Any] | None = None,
    activate: bool = True,
) -> dict[str, Any]:
    """Create a custom preset for the selected endpoint and model."""

    normalized_endpoint = normalize_openai_endpoint_url(endpoint_url)
    normalized_model = str(model_name or "").strip()
    if not normalized_model:
        raise ValueError("Model name is required for OpenAI presets")

    base_name = str(name or "").strip() or _next_custom_preset_name(normalized_endpoint, normalized_model)

    # Start custom presets from normalized input or the built-in baseline.
    try:
        preset = OpenAiPreset.objects.create(
            endpoint_url=normalized_endpoint,
            model_name=normalized_model,
            name=base_name,
            config=normalize_openai_preset_config(config) or deepcopy(DEFAULT_OPENAI_PRESET_CONFIG),
            is_default=False,
            is_active=False,
        )
    except IntegrityError as exc:
        raise ValueError(f"A preset named '{base_name}' already exists for {normalized_model}.") from exc

    if activate:
        return activate_openai_preset(normalized_endpoint, normalized_model, str(preset.id))

    return get_openai_preset_payload(normalized_endpoint, normalized_model)


# Rename a custom preset.
@transaction.atomic
def rename_openai_preset(endpoint_url: str, model_name: str, preset_id: str, new_name: str) -> dict[str, Any]:
    """Rename a custom preset without changing its config."""

    normalized_endpoint = normalize_openai_endpoint_url(endpoint_url)
    normalized_name = str(new_name or "").strip()
    if not normalized_name:
        raise ValueError("Preset name cannot be empty")

    presets, _active_preset = ensure_openai_preset_state(normalized_endpoint, model_name)
    preset = _get_preset_by_id(presets, preset_id)
    if preset.is_default:
        raise ValueError("The default preset cannot be renamed")

    preset.name = normalized_name
    try:
        preset.save(update_fields=["name", "updated_at"])
    except IntegrityError as exc:
        raise ValueError(f"A preset named '{normalized_name}' already exists for {model_name}.") from exc

    return get_openai_preset_payload(normalized_endpoint, model_name)


# Delete a custom preset.
@transaction.atomic
def delete_openai_preset(endpoint_url: str, model_name: str, preset_id: str) -> dict[str, Any]:
    """Delete a custom preset and restore the default when needed."""

    normalized_endpoint = normalize_openai_endpoint_url(endpoint_url)
    presets, _active_preset = ensure_openai_preset_state(normalized_endpoint, model_name)
    preset = _get_preset_by_id(presets, preset_id)
    if preset.is_default:
        raise ValueError("The default preset cannot be deleted")

    was_active = preset.is_active
    preset.delete()

    payload = get_openai_preset_payload(normalized_endpoint, model_name)
    if not was_active:
        return payload

    default_preset = next(item for item in payload["presets"] if item.get("is_default"))
    return activate_openai_preset(normalized_endpoint, model_name, default_preset["id"])


# Persist changes into the active preset.
@transaction.atomic
def sync_active_openai_preset(endpoint_url: str, model_name: str, config: dict[str, Any]) -> dict[str, Any]:
    """Persist UI changes into the active preset."""

    normalized_endpoint = normalize_openai_endpoint_url(endpoint_url)
    normalized_model = str(model_name or "").strip()
    normalized_config = normalize_openai_preset_config(config)
    presets, active_preset = ensure_openai_preset_state(normalized_endpoint, normalized_model)

    # Editing the default preset should create a custom active copy.
    if active_preset.is_default:
        if normalize_openai_preset_config(active_preset.config) == normalized_config:
            return get_openai_preset_payload(normalized_endpoint, normalized_model)

        return create_openai_preset(
            normalized_endpoint,
            normalized_model,
            config=normalized_config,
            activate=True,
        )

    # Custom active presets can be updated in place.
    active_preset.config = normalized_config
    active_preset.save(update_fields=["config", "updated_at"])
    return get_openai_preset_payload(normalized_endpoint, normalized_model)
