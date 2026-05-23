# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Apps.UI import host_theme_bridge
from Settings import host_theme


class HostThemeBridgeTests(unittest.TestCase):
    """Tests for host theme → CSS normalization (ASLM MAUI hex formats)."""

    def test_normalize_argb_opaque_to_hex(self) -> None:
        self.assertEqual(host_theme_bridge.normalize_color_to_css("#FF0A84FF"), "#0a84ff")

    def test_normalize_argb_transparent_to_rgba(self) -> None:
        out = host_theme_bridge.normalize_color_to_css("#99EBEBF5")
        self.assertTrue(out.startswith("rgba("))
        self.assertIn("235", out)

    def test_normalize_six_digit(self) -> None:
        self.assertEqual(host_theme_bridge.normalize_color_to_css("#1C1C1E"), "#1c1c1e")

    def test_normalize_three_digit(self) -> None:
        self.assertEqual(host_theme_bridge.normalize_color_to_css("#F0A"), "#ff00aa")

    def test_normalize_invalid_returns_none(self) -> None:
        self.assertIsNone(host_theme_bridge.normalize_color_to_css("not-a-color"))
        self.assertIsNone(host_theme_bridge.normalize_color_to_css(""))
        self.assertIsNone(host_theme_bridge.normalize_color_to_css(None))

    def test_css_color_to_srgb_channels_hex(self) -> None:
        self.assertEqual(host_theme_bridge.css_color_to_srgb_channels("#000000"), (0.0, 0.0, 0.0))
        self.assertEqual(host_theme_bridge.css_color_to_srgb_channels("#ffffff"), (1.0, 1.0, 1.0))

    def test_css_color_to_srgb_channels_rgba(self) -> None:
        self.assertEqual(
            host_theme_bridge.css_color_to_srgb_channels("rgba(10, 20, 30, 0.5)"),
            (10 / 255.0, 20 / 255.0, 30 / 255.0),
        )

    def test_infer_prefer_light_activity_surfaces_uses_canvas_luminance(self) -> None:
        """A light canvas should pick light activity tokens even if ``theme`` says dark."""

        resolved = {"--c-bg": "#ffffff"}
        self.assertTrue(host_theme_bridge.infer_prefer_light_activity_surfaces(resolved, "dark"))

    def test_infer_prefer_light_activity_surfaces_falls_back_to_theme(self) -> None:
        self.assertFalse(host_theme_bridge.infer_prefer_light_activity_surfaces({}, "dark"))
        self.assertTrue(host_theme_bridge.infer_prefer_light_activity_surfaces({}, "light"))

    def test_build_context_from_payload(self) -> None:
        payload = {
            "appearance": "Dark",
            "theme": "dark",
            "colors": {
                "BackgroundPrimary": "#FF000000",
                "SystemBlue": "#FF0A84FF",
                "ActionBlue": "#FF1188FF",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "host_theme.json"
            original = host_theme.HOST_THEME_FILE
            host_theme.HOST_THEME_FILE = path
            try:
                host_theme.save_host_theme_payload(payload)
                ctx = host_theme_bridge.build_host_theme_template_context()
                self.assertTrue(ctx["host_theme_available"])
                self.assertEqual(ctx["host_theme_effective"], "dark")
                self.assertIn("--c-bg: #000000", ctx["host_theme_css_variables"])
                self.assertIn("--c-system-blue: #0a84ff", ctx["host_theme_css_variables"])
                self.assertIn("--c-primary: #1188ff", ctx["host_theme_css_variables"])
                self.assertIn("--activity-card-bg: color-mix(in srgb, var(--c-text) 4.5%, transparent)", ctx["host_theme_css_variables"])
                self.assertIn(
                    "--activity-card-border: color-mix(in srgb, var(--c-text) 10.5%, transparent)",
                    ctx["host_theme_css_variables"],
                )
                self.assertIn(
                    "--activity-card-inner-bg: color-mix(in srgb, var(--c-black) 18%, transparent)",
                    ctx["host_theme_css_variables"],
                )
                self.assertIn(
                    "--activity-icon-bg: color-mix(in srgb, var(--surface-secondary) 94%, var(--c-text) 6%)",
                    ctx["host_theme_css_variables"],
                )
                self.assertIn(
                    "--activity-preview-action-bg: color-mix(in srgb, var(--surface-secondary) 86%, var(--c-primary) 14%)",
                    ctx["host_theme_css_variables"],
                )
                self.assertIn(
                    "--activity-image-frame-bg: color-mix(in srgb, var(--surface-secondary) 94%, var(--c-text) 6%)",
                    ctx["host_theme_css_variables"],
                )
                self.assertIn(
                    "--activity-media-control-bg: color-mix(in srgb, var(--surface-secondary) 88%, var(--c-text) 12%)",
                    ctx["host_theme_css_variables"],
                )
                self.assertIn("--activity-on-surface: var(--c-text)", ctx["host_theme_css_variables"])
                self.assertIn("--activity-monochrome-svg-filter: none", ctx["host_theme_css_variables"])
            finally:
                host_theme.HOST_THEME_FILE = original

    def test_build_context_uses_light_activity_inner_surfaces(self) -> None:
        payload = {
            "appearance": "Custom",
            "theme": "light",
            "colors": {
                "BackgroundPrimary": "#FFF2F2F7",
                "BackgroundSecondary": "#FFFFFFFF",
                "LabelPrimary": "#FF000000",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "host_theme.json"
            original = host_theme.HOST_THEME_FILE
            host_theme.HOST_THEME_FILE = path
            try:
                host_theme.save_host_theme_payload(payload)
                ctx = host_theme_bridge.build_host_theme_template_context()
                self.assertIn("--activity-card-bg: var(--surface-secondary)", ctx["host_theme_css_variables"])
                self.assertIn("--activity-card-subtle-bg: var(--surface-secondary)", ctx["host_theme_css_variables"])
                self.assertIn(
                    "--activity-card-bg-hover: color-mix(in srgb, var(--surface-secondary) 94%, var(--c-primary) 6%)",
                    ctx["host_theme_css_variables"],
                )
                self.assertIn(
                    "--activity-card-inner-bg: color-mix(in srgb, var(--c-text) 4.5%, transparent)",
                    ctx["host_theme_css_variables"],
                )
                self.assertIn(
                    "--activity-card-border: color-mix(in srgb, var(--surface-secondary) 94%, var(--c-text) 6%)",
                    ctx["host_theme_css_variables"],
                )
                self.assertIn(
                    "--activity-card-border-hover: color-mix(in srgb, var(--surface-secondary) 86%, var(--c-primary) 14%)",
                    ctx["host_theme_css_variables"],
                )
                self.assertIn(
                    "--activity-card-inner-bg-strong: color-mix(in srgb, var(--c-text) 6.5%, transparent)",
                    ctx["host_theme_css_variables"],
                )
                self.assertIn(
                    "--activity-monochrome-svg-filter: brightness(0) saturate(100%)",
                    ctx["host_theme_css_variables"],
                )
            finally:
                host_theme.HOST_THEME_FILE = original

    def test_build_context_light_activity_when_canvas_is_light_despite_dark_theme(self) -> None:
        payload = {
            "appearance": "Dark",
            "theme": "dark",
            "colors": {
                "BackgroundPrimary": "#FFFFFFFF",
                "BackgroundSecondary": "#FFF2F2F7",
                "LabelPrimary": "#FF000000",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "host_theme.json"
            original = host_theme.HOST_THEME_FILE
            host_theme.HOST_THEME_FILE = path
            try:
                host_theme.save_host_theme_payload(payload)
                ctx = host_theme_bridge.build_host_theme_template_context()
                self.assertEqual(ctx["host_theme_effective"], "dark")
                self.assertIn("--activity-card-bg: var(--surface-secondary)", ctx["host_theme_css_variables"])
                self.assertIn(
                    "--activity-card-inner-bg: color-mix(in srgb, var(--c-text) 4.5%, transparent)",
                    ctx["host_theme_css_variables"],
                )
                self.assertIn(
                    "--activity-monochrome-svg-filter: brightness(0) saturate(100%)",
                    ctx["host_theme_css_variables"],
                )
            finally:
                host_theme.HOST_THEME_FILE = original

    def test_host_theme_json_is_safe_for_script_tag(self) -> None:
        payload = {
            "appearance": "Dark",
            "theme": "dark",
            "customThemeName": "</script><script>alert(1)</script>",
            "colors": {"BackgroundPrimary": "#FF000000"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "host_theme.json"
            original = host_theme.HOST_THEME_FILE
            host_theme.HOST_THEME_FILE = path
            try:
                host_theme.save_host_theme_payload(payload)
                ctx = host_theme_bridge.build_host_theme_template_context()
                self.assertNotIn("</script>", ctx["host_theme_json"].lower())
                self.assertIn("\\u003c/script\\u003e", ctx["host_theme_json"].lower())
            finally:
                host_theme.HOST_THEME_FILE = original


class HostThemePersistenceTests(unittest.TestCase):
    """Regression tests for ASLM host theme snapshot persistence."""

    def test_round_trip_via_save_and_load(self) -> None:
        """save_host_theme_payload followed by load_host_theme returns equivalent data."""

        payload = {
            "appearance": "Dark",
            "theme": "dark",
            "colors": {"BackgroundPrimary": "#FF000000"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "host_theme.json"
            original = host_theme.HOST_THEME_FILE
            host_theme.HOST_THEME_FILE = path
            try:
                host_theme.save_host_theme_payload(payload)
                loaded = host_theme.load_host_theme()
                self.assertIsNotNone(loaded)
                self.assertEqual(loaded.get("theme"), "dark")
                self.assertEqual(loaded.get("appearance"), "Dark")
                self.assertEqual(loaded.get("colors", {}).get("BackgroundPrimary"), "#FF000000")
            finally:
                host_theme.HOST_THEME_FILE = original

    def test_load_host_theme_missing_returns_none(self) -> None:
        """When the snapshot file does not exist, load_host_theme returns None."""

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            original = host_theme.HOST_THEME_FILE
            host_theme.HOST_THEME_FILE = path
            try:
                self.assertIsNone(host_theme.load_host_theme())
            finally:
                host_theme.HOST_THEME_FILE = original

    def test_load_host_theme_invalid_json_returns_none(self) -> None:
        """Corrupt JSON yields None and does not raise."""

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "host_theme.json"
            path.write_text("{not json", encoding="utf-8")
            original = host_theme.HOST_THEME_FILE
            host_theme.HOST_THEME_FILE = path
            try:
                self.assertIsNone(host_theme.load_host_theme())
            finally:
                host_theme.HOST_THEME_FILE = original

    def test_load_host_theme_strips_utf8_bom(self) -> None:
        """A UTF-8 BOM prefix must not break parsing (e.g. legacy writes from other tools)."""

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "host_theme.json"
            path.write_bytes(b"\xef\xbb\xbf" + b'{"theme":"light","colors":{}}')
            original = host_theme.HOST_THEME_FILE
            host_theme.HOST_THEME_FILE = path
            try:
                loaded = host_theme.load_host_theme()
                self.assertIsNotNone(loaded)
                self.assertEqual(loaded.get("theme"), "light")
            finally:
                host_theme.HOST_THEME_FILE = original


if __name__ == "__main__":
    unittest.main()
