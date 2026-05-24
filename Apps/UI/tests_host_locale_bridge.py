# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from Apps.UI import host_locale_bridge
from Settings import host_locale


class HostLocaleBridgeTests(unittest.TestCase):
  def test_is_rtl_arabic(self) -> None:
    self.assertTrue(host_locale_bridge.is_rtl_language("ar"))

  def test_is_rtl_english(self) -> None:
    self.assertFalse(host_locale_bridge.is_rtl_language("en"))

  def test_language_to_html_lang(self) -> None:
    self.assertEqual(host_locale_bridge.language_to_html_lang("zh-Hans"), "zh-hans")

  def test_build_context_arabic_rtl(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "host_locale.json"
      path.write_text(
        json.dumps({"language": "ar", "displayName": "العربية"}),
        encoding="utf-8",
      )
      with mock.patch.object(host_locale, "HOST_LOCALE_FILE", path):
        ctx = host_locale_bridge.build_host_locale_template_context()
    self.assertEqual(ctx["text_direction"], "rtl")
    self.assertTrue(ctx["host_locale_is_rtl"])
    self.assertEqual(ctx["host_language_effective"], "ar")
    self.assertEqual(ctx["html_lang"], "ar")

  def test_build_context_russian_uses_ru_catalog(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "host_locale.json"
      path.write_text(
        json.dumps({"language": "ru", "displayName": "Русский"}),
        encoding="utf-8",
      )
      with mock.patch.object(host_locale, "HOST_LOCALE_FILE", path):
        ctx = host_locale_bridge.build_host_locale_template_context()
    self.assertEqual(ctx["host_language_raw"], "ru")
    self.assertEqual(ctx["host_language_effective"], "ru")
    self.assertEqual(ctx["text_direction"], "ltr")
    payload = json.loads(ctx["host_locale_json"])
    self.assertNotEqual(
      payload["messages"]["sidebar"]["newChat"],
      "New Chat",
    )

  def test_json_script_escaping(self) -> None:
    payload = json.loads(host_locale_bridge.build_host_locale_template_context()["host_locale_json"])
    self.assertIn("messages", payload)
    self.assertIn("sidebar", payload["messages"])
