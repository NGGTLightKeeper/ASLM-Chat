# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

from django import template
from django.templatetags.static import static as django_static

from Apps.UI import STATIC_CACHE_VERSION
from Apps.UI.locale_catalog import translate

register = template.Library()


def append_static_cache_version(url: str) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}v={STATIC_CACHE_VERSION}"


@register.simple_tag
def static(path: str) -> str:
    """Resolve a static asset URL with the per-process cache-bust query."""

    return append_static_cache_version(django_static(path))


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
