# Copyright NGGT.LightKeeper. All Rights Reserved.

"""Map ASLM ``host_theme.json`` (see ASLM ``ThemePaletteResolver`` / ``ModuleThemePayloadBuilder``) to Django template context and CSS custom properties."""

from __future__ import annotations

import json
import re
from typing import Any, Final

from Settings.host_theme import load_host_theme

# Sync with ASLM ThemePaletteResolver / Colors.xaml when adding host palette keys.
_ASLM_COLOR_KEY_TO_CSS_VAR: Final[dict[str, str]] = {
    "SystemBlue": "--c-system-blue",
    "SystemGreen": "--c-system-green",
    "SystemIndigo": "--c-system-indigo",
    "SystemOrange": "--c-system-orange",
    "SystemPink": "--c-system-pink",
    "SystemPurple": "--c-system-purple",
    "SystemRed": "--c-system-red",
    "SystemTeal": "--c-system-teal",
    "SystemYellow": "--c-system-yellow",
    "SystemMint": "--c-system-mint",
    "SystemGray": "--c-gray-1",
    "SystemGray2": "--c-gray-2",
    "SystemGray3": "--c-gray-3",
    "SystemGray4": "--c-gray-4",
    "SystemGray5": "--c-gray-5",
    "SystemGray6": "--c-gray-6",
    "BackgroundPrimary": "--c-bg",
    "BackgroundSecondary": "--c-bg-surface",
    "BackgroundTertiary": "--c-bg-elevated",
    "LabelPrimary": "--c-text",
    "LabelSecondary": "--c-text-muted",
    "LabelTertiary": "--c-text-dim",
    "LabelQuaternary": "--c-text-quaternary",
    "PlaceholderText": "--c-text-placeholder",
    "Separator": "--c-border",
    "LinkColor": "--c-link",
    "SystemBlueOverlay": "--c-overlay-blue",
    "White": "--c-white",
    "Black": "--c-black",
    "ActionRed": "--c-danger",
    "ActionBlue": "--c-primary",
    "ActionGreen": "--c-success",
    "OverlayBackground": "--c-overlay-scrim",
    "BackgroundErrorOverlay": "--c-bg-error-overlay",
}

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def normalize_color_to_css(raw: str | None) -> str | None:
    """Convert MAUI / ASLM hex strings to a CSS color (``#rrggbb`` or ``rgba(...)``)."""

    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if not _HEX_RE.match(s):
        return None
    body = s[1:]
    if len(body) == 3:
        r = int(body[0] + body[0], 16)
        g = int(body[1] + body[1], 16)
        b = int(body[2] + body[2], 16)
        return f"#{r:02x}{g:02x}{b:02x}"
    if len(body) == 6:
        return f"#{body.lower()}"
    # #AARRGGBB (MAUI ToHex)
    aa = int(body[0:2], 16)
    rr = int(body[2:4], 16)
    gg = int(body[4:6], 16)
    bb = int(body[6:8], 16)
    if aa == 255:
        return f"#{rr:02x}{gg:02x}{bb:02x}"
    alpha = round(aa / 255, 4)
    return f"rgba({rr}, {gg}, {bb}, {alpha})"


def _effective_theme(payload: dict[str, Any]) -> str:
    theme = str(payload.get("theme") or "").strip().lower()
    if theme in {"light", "dark"}:
        return theme
    appearance = str(payload.get("appearance") or "").strip().lower()
    if appearance == "light":
        return "light"
    return "dark"


def build_host_theme_template_context() -> dict[str, Any]:
    """Return keys for ``base.html``: CSS variable block, color-scheme, optional JSON."""

    raw = load_host_theme()
    if not isinstance(raw, dict):
        return _empty_context()

    colors = raw.get("colors")
    if not isinstance(colors, dict):
        return _empty_context()

    resolved: dict[str, str] = {}
    for aslm_key, css_var in _ASLM_COLOR_KEY_TO_CSS_VAR.items():
        val = colors.get(aslm_key)
        if val is None:
            continue
        css_color = normalize_color_to_css(str(val))
        if css_color is None:
            continue
        resolved[css_var] = css_color

    if not resolved:
        return _empty_context()

    if "--c-system-teal" in resolved:
        resolved["--c-system-cyan"] = resolved["--c-system-teal"]

    theme = _effective_theme(raw)

    declarations = [f"  {var}: {value};" for var, value in resolved.items()]

    # Derived soft surfaces from semantic colors (override static rgba tied to old blue).
    declarations.append("  --surface-blue-soft: color-mix(in srgb, var(--c-primary) 10%, transparent);")
    declarations.append(
        "  --c-overlay-blue-strong: color-mix(in srgb, var(--c-primary) 16%, transparent);"
    )
    declarations.append("  --focus-ring: color-mix(in srgb, var(--c-primary) 18%, transparent);")
    declarations.append(
        "  --surface-purple-soft: color-mix(in srgb, var(--c-system-purple) 12%, transparent);"
    )
    declarations.append(
        "  --surface-purple-strong: color-mix(in srgb, var(--c-system-purple) 15%, transparent);"
    )
    declarations.append(
        "  --surface-green-soft: color-mix(in srgb, var(--c-success) 8%, transparent);"
    )
    declarations.append(
        "  --border-success: color-mix(in srgb, var(--c-success) 40%, transparent);"
    )
    declarations.append(
        "  --text-success: color-mix(in srgb, var(--c-success) 85%, transparent);"
    )

    inner = "\n".join(declarations)
    host_theme_css_variables = f":root {{\n{inner}\n}}"

    meta = {
        "theme": theme,
        "appearance": str(raw.get("appearance") or ""),
        "customThemeId": raw.get("customThemeId"),
        "customThemeName": raw.get("customThemeName"),
    }
    safe_json = json.dumps(meta, ensure_ascii=False)

    return {
        "host_theme_available": True,
        "host_theme_effective": theme,
        "host_theme_css_variables": host_theme_css_variables,
        "host_theme_json": safe_json,
    }


def _empty_context() -> dict[str, Any]:
    return {
        "host_theme_available": False,
        "host_theme_effective": "dark",
        "host_theme_css_variables": "",
        "host_theme_json": "{}",
    }
