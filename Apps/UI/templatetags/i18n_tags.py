# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

from django import template
from Apps.UI.locale_catalog import translate

register = template.Library()


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
