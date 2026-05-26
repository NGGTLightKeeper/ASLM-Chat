# Copyright NGGT.LightKeeper. All Rights Reserved.

"""Load UI locale JSON catalogs and resolve translations with English fallback."""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from Settings.host_locale import get_language, normalize_host_language

logger = logging.getLogger(__name__)

LOCALES_DIR = Path(__file__).resolve().parent / "locales"
BASE_LOCALE = "en"
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _locale_file_path(locale: str) -> Path:
    return LOCALES_DIR / f"{locale}.json"


def list_available_chat_locales() -> list[str]:
    """Return locale codes that have a catalog file on disk."""

    if not LOCALES_DIR.is_dir():
        return [BASE_LOCALE]
    codes = sorted(
        path.stem
        for path in LOCALES_DIR.glob("*.json")
        if path.is_file() and not path.name.endswith(".tmp")
    )
    return codes or [BASE_LOCALE]


def resolve_effective_locale(host_language: str | None) -> str:
    """Map host language to a Chat catalog file, falling back to English."""

    normalized = normalize_host_language(host_language)
    if _locale_file_path(normalized).is_file():
        return normalized
    return BASE_LOCALE


def resolve_effective_locale_from_snapshot() -> str:
    return resolve_effective_locale(get_language())


@lru_cache(maxsize=32)
def _load_raw_catalog(locale: str) -> dict[str, Any]:
    path = _locale_file_path(locale)
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read locale file %s: %s", path, exc)
        return {}
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Could not parse locale file %s: %s", path, exc)
        return {}
    return raw if isinstance(raw, dict) else {}


def load_catalog(locale: str) -> dict[str, Any]:
    """Return merged messages for ``locale`` with English as the base layer."""

    base = _load_raw_catalog(BASE_LOCALE)
    if locale == BASE_LOCALE:
        return base
    overlay = _load_raw_catalog(locale)
    return _deep_merge(base, overlay)


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _lookup_nested(catalog: dict[str, Any], key: str) -> Any | None:
    current: Any = catalog
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _interpolate(template: str, params: dict[str, Any]) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in params:
            return match.group(0)
        return str(params[name])

    return _PLACEHOLDER_RE.sub(repl, template)


def translate(key: str, *, locale: str | None = None, fallback: str | None = None, **params: Any) -> str:
    """Resolve a dot-path key with optional ``{name}`` placeholders."""

    effective = resolve_effective_locale(locale) if locale else resolve_effective_locale_from_snapshot()
    catalog = load_catalog(effective)
    value = _lookup_nested(catalog, key)
    if value is None and effective != BASE_LOCALE:
        value = _lookup_nested(load_catalog(BASE_LOCALE), key)
    if value is None:
        if fallback is not None:
            return _interpolate(fallback, params) if params else fallback
        return key
    if not isinstance(value, str):
        return str(value)
    if params:
        return _interpolate(value, params)
    return value


def catalog_for_js(locale: str | None = None) -> dict[str, Any]:
    """Return the merged catalog tree embedded in pages for client-side ``t()``."""

    effective = resolve_effective_locale(locale) if locale else resolve_effective_locale_from_snapshot()
    return load_catalog(effective)
