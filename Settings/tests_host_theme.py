# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Settings import host_theme


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
