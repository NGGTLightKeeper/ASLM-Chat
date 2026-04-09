# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.db import IntegrityError, transaction

from API import lms as lms_api
from Apps.Data.models import LmsPreset

DEFAULT_LMS_PRESET_NAME = "Default"
DEFAULT_LMS_PRESET_CONFIG: dict[str, Any] = {
    "operation": {},
}


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


def normalize_lms_preset_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact LM Studio preset config ready for storage."""

    if not isinstance(config, dict):
        return deepcopy(DEFAULT_LMS_PRESET_CONFIG)

    operation_config = config.get("operation")
    if not isinstance(operation_config, dict):
        operation_config = {
            key: value
            for key, value in config.items()
            if key != "load"
        }

    normalized = {
        "operation": _normalize_config_value(deepcopy(operation_config)) or {},
    }
    return normalized


def _get_default_lms_preset_config(model_name: str) -> dict[str, Any]:
    """Read the default LM Studio config baked into the selected model."""

    settings_payload = lms_api.get_model_settings(model_name)
    return normalize_lms_preset_config(
        {
            "operation": settings_payload.get("defaults", {}) or {},
        }
    )


def _next_custom_preset_name(model_name: str) -> str:
    """Generate the next free custom preset name for a model."""

    existing_names = set(
        LmsPreset.objects.filter(model_name=model_name).values_list("name", flat=True)
    )
    index = 1

    while True:
        candidate = f"Custom {index}"
        if candidate not in existing_names:
            return candidate
        index += 1


def _serialize_preset(preset: LmsPreset) -> dict[str, Any]:
    """Convert a preset model into the frontend JSON shape."""

    return {
        "id": str(preset.id),
        "model_name": preset.model_name,
        "name": preset.name,
        "config": normalize_lms_preset_config(preset.config or {}),
        "is_default": preset.is_default,
        "is_active": preset.is_active,
    }


def _get_preset_by_id(presets: list[LmsPreset], preset_id: str) -> LmsPreset:
    """Return one preset from a loaded list or raise when it is missing."""

    preset = next((item for item in presets if str(item.id) == str(preset_id)), None)
    if preset is None:
        raise LmsPreset.DoesNotExist("Preset not found")
    return preset


@transaction.atomic
def ensure_lms_preset_state(model_name: str) -> tuple[list[LmsPreset], LmsPreset]:
    """Ensure a model has one default preset and one active preset."""

    normalized_model = str(model_name or "").strip()
    if not normalized_model:
        raise ValueError("Model name is required for LM Studio presets")

    presets = list(
        LmsPreset.objects.select_for_update()
        .filter(model_name=normalized_model)
        .order_by("-is_active", "-is_default", "name")
    )

    if not presets:
        default_preset = LmsPreset.objects.create(
            model_name=normalized_model,
            name=DEFAULT_LMS_PRESET_NAME,
            config=_get_default_lms_preset_config(normalized_model),
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
            if preset.pk == active_preset.pk or not preset.is_active:
                continue
            preset.is_active = False
            preset.save(update_fields=["is_active"])

    presets = list(
        LmsPreset.objects.filter(model_name=normalized_model)
        .order_by("-is_active", "-is_default", "name")
    )
    return presets, active_preset


def get_lms_preset_payload(model_name: str) -> dict[str, Any]:
    """Return presets and the active config for the selected model."""

    presets, active_preset = ensure_lms_preset_state(model_name)
    return {
        "model": model_name,
        "active_preset_id": str(active_preset.id),
        "presets": [_serialize_preset(preset) for preset in presets],
        "active_config": normalize_lms_preset_config(active_preset.config or {}),
    }


@transaction.atomic
def activate_lms_preset(model_name: str, preset_id: str) -> dict[str, Any]:
    """Mark one preset as active for its model."""

    presets, _active_preset = ensure_lms_preset_state(model_name)
    preset = _get_preset_by_id(presets, preset_id)

    LmsPreset.objects.filter(model_name=model_name, is_active=True).exclude(pk=preset.pk).update(
        is_active=False
    )
    if not preset.is_active:
        preset.is_active = True
        preset.save(update_fields=["is_active"])

    return get_lms_preset_payload(model_name)


@transaction.atomic
def create_lms_preset(
    model_name: str,
    *,
    name: str | None = None,
    config: dict[str, Any] | None = None,
    activate: bool = True,
) -> dict[str, Any]:
    """Create a custom preset for the selected model."""

    normalized_model = str(model_name or "").strip()
    if not normalized_model:
        raise ValueError("Model name is required for LM Studio presets")

    base_name = str(name or "").strip() or _next_custom_preset_name(normalized_model)

    try:
        preset = LmsPreset.objects.create(
            model_name=normalized_model,
            name=base_name,
            config=normalize_lms_preset_config(config) or _get_default_lms_preset_config(normalized_model),
            is_default=False,
            is_active=False,
        )
    except IntegrityError as exc:
        raise ValueError(f"A preset named '{base_name}' already exists for {normalized_model}.") from exc

    if activate:
        return activate_lms_preset(normalized_model, str(preset.id))

    return get_lms_preset_payload(normalized_model)


@transaction.atomic
def rename_lms_preset(model_name: str, preset_id: str, new_name: str) -> dict[str, Any]:
    """Rename a custom preset without changing its config."""

    normalized_name = str(new_name or "").strip()
    if not normalized_name:
        raise ValueError("Preset name cannot be empty")

    presets, _active_preset = ensure_lms_preset_state(model_name)
    preset = _get_preset_by_id(presets, preset_id)
    if preset.is_default:
        raise ValueError("The default preset cannot be renamed")

    preset.name = normalized_name
    try:
        preset.save(update_fields=["name", "updated_at"])
    except IntegrityError as exc:
        raise ValueError(f"A preset named '{normalized_name}' already exists for {model_name}.") from exc

    return get_lms_preset_payload(model_name)


@transaction.atomic
def delete_lms_preset(model_name: str, preset_id: str) -> dict[str, Any]:
    """Delete a custom preset and restore the default when needed."""

    presets, _active_preset = ensure_lms_preset_state(model_name)
    preset = _get_preset_by_id(presets, preset_id)
    if preset.is_default:
        raise ValueError("The default preset cannot be deleted")

    was_active = preset.is_active
    preset.delete()

    payload = get_lms_preset_payload(model_name)
    if not was_active:
        return payload

    default_preset = next(item for item in payload["presets"] if item.get("is_default"))
    return activate_lms_preset(model_name, default_preset["id"])


@transaction.atomic
def sync_active_lms_preset(model_name: str, config: dict[str, Any]) -> dict[str, Any]:
    """Persist UI changes into the active preset."""

    normalized_model = str(model_name or "").strip()
    normalized_config = normalize_lms_preset_config(config)
    presets, active_preset = ensure_lms_preset_state(normalized_model)

    if active_preset.is_default:
        if normalize_lms_preset_config(active_preset.config) == normalized_config:
            return get_lms_preset_payload(normalized_model)

        return create_lms_preset(
            normalized_model,
            config=normalized_config,
            activate=True,
        )

    active_preset.config = normalized_config
    active_preset.save(update_fields=["config", "updated_at"])
    return get_lms_preset_payload(normalized_model)
