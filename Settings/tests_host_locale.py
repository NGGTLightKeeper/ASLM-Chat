# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from Settings import host_locale


class HostLocaleTests(unittest.TestCase):
  def test_save_and_load_round_trip(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "host_locale.json"
      with mock.patch.object(host_locale, "HOST_LOCALE_FILE", path):
        host_locale.save_host_locale_payload({"language": "ru", "displayName": "Русский"})
        payload = host_locale.load_host_locale()
      self.assertIsNotNone(payload)
      assert payload is not None
      self.assertEqual(payload["language"], "ru")
      self.assertEqual(payload["displayName"], "Русский")

  def test_load_strips_bom(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "host_locale.json"
      path.write_text('\ufeff{"language": "en", "displayName": "English"}\n', encoding="utf-8")
      with mock.patch.object(host_locale, "HOST_LOCALE_FILE", path):
        payload = host_locale.load_host_locale()
      self.assertEqual(payload, {"language": "en", "displayName": "English"})

  def test_get_language_defaults_to_en(self) -> None:
    with mock.patch.object(host_locale, "load_host_locale", return_value=None):
      self.assertEqual(host_locale.get_language(), "en")

  def test_normalize_host_language_unknown(self) -> None:
    self.assertEqual(host_locale.normalize_host_language("xx-YY"), "en")

  def test_normalize_host_language_case_insensitive(self) -> None:
    self.assertEqual(host_locale.normalize_host_language("PT-br"), "pt-BR")
