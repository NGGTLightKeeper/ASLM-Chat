# Copyright NGGT.LightKeeper. All Rights Reserved.

"""Map ASLM ``host_locale.json`` to Django template context and client bootstrap JSON."""

from __future__ import annotations

import json
from typing import Any, Final

from Apps.UI.locale_catalog import (
    catalog_for_js,
    resolve_effective_locale_from_snapshot,
    translate,
)
from Settings.host_locale import get_display_name, get_language, load_host_locale

# Sync with ASLM AppLocalizationService.RtlLanguageCodes.
_RTL_LANGUAGE_CODES: Final[frozenset[str]] = frozenset({"ar"})

# Primary subtags that are typically written right-to-left (future host languages).
_RTL_PRIMARY_SUBTAGS: Final[frozenset[str]] = frozenset(
    {"ar", "he", "fa", "ur", "ps", "sd", "yi", "dv", "ku"}
)


def is_rtl_language(language_code: str | None) -> bool:
    """Return whether the UI should use right-to-left layout."""

    code = (language_code or "en").strip()
    if not code:
        return False
    if code in _RTL_LANGUAGE_CODES:
        return True
    for existing in _RTL_LANGUAGE_CODES:
        if code.lower() == existing.lower():
            return True
    primary = code.split("-", 1)[0].lower()
    return primary in _RTL_PRIMARY_SUBTAGS


def language_to_html_lang(language_code: str) -> str:
    """Convert BCP-47 to a value suitable for the HTML ``lang`` attribute."""

    parts = language_code.split("-", 1)
    if len(parts) == 1:
        return parts[0].lower()
    primary, region = parts
    if len(region) == 4 and region.isalpha():
        return f"{primary.lower()}-{region.lower()}"
    return f"{primary.lower()}-{region}"


def build_host_locale_template_context() -> dict[str, Any]:
    """Return keys for ``base.html`` and the client locale bootstrap."""

    raw = load_host_locale()
    host_language_raw = get_language()
    effective = resolve_effective_locale_from_snapshot()
    display_name = get_display_name()
    # Layout direction follows the host language even when Chat falls back to English strings.
    rtl = is_rtl_language(host_language_raw)
    messages = catalog_for_js(effective)

    meta = {
        "available": raw is not None,
        "language": host_language_raw,
        "effectiveLocale": effective,
        "displayName": display_name or "",
        "isRtl": rtl,
        "textDirection": "rtl" if rtl else "ltr",
        "htmlLang": language_to_html_lang(host_language_raw),
        "messages": messages,
    }

    return {
        "host_locale_available": raw is not None,
        "host_language_raw": host_language_raw,
        "host_language_effective": effective,
        "host_locale_display_name": display_name or "",
        "host_locale_is_rtl": rtl,
        "html_lang": language_to_html_lang(host_language_raw),
        "text_direction": "rtl" if rtl else "ltr",
        "host_locale_json": _json_for_script_tag(meta),
        "locale_t": translate,
    }


def _json_for_script_tag(value: dict[str, Any]) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
