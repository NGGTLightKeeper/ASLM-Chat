# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from django import template
from django.templatetags.static import static as django_static
from django.utils.safestring import mark_safe

from Apps.UI import STATIC_CACHE_VERSION
from Apps.UI.locale_catalog import translate

register = template.Library()
_STATIC_JS_ROOT = Path(__file__).resolve().parents[1] / "static" / "js"


def append_static_cache_version(url: str) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}v={STATIC_CACHE_VERSION}"


@register.simple_tag
def static(path: str) -> str:
    """Resolve a static asset URL with the per-process cache-bust query."""

    return append_static_cache_version(django_static(path))


@lru_cache(maxsize=1)
def _static_import_map_json() -> str:
    """Map every local ES module URL to the current backend cache version."""

    imports: dict[str, str] = {}
    for module_path in sorted(_STATIC_JS_ROOT.rglob("*.js")):
        relative_path = module_path.relative_to(_STATIC_JS_ROOT.parent).as_posix()
        source_url = django_static(relative_path)
        imports[source_url] = append_static_cache_version(source_url)
    return json.dumps(
        {"imports": imports},
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("<", "\\u003c")


@register.simple_tag
def static_import_map() -> str:
    """Return a process-versioned import map for the complete local JS graph."""

    return mark_safe(_static_import_map_json())


@register.simple_tag(takes_context=True)
def t(context: template.Context, key: str) -> str:
    """Translate ``key`` using the effective locale from template context."""

    locale = context.get("host_language_effective")
    return translate(key, locale=locale)


@register.simple_tag(takes_context=True)
def t_param(context: template.Context, key: str, **kwargs: str) -> str:
    """Translate ``key`` with ``{name}`` placeholders."""

    locale = context.get("host_language_effective")
    return translate(key, locale=locale, **kwargs)
