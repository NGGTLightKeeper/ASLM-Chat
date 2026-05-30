# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import unittest

from Apps.UI import locale_catalog


class LocaleCatalogTests(unittest.TestCase):
  # Verify resolve effective locale without translation file.
  def test_resolve_effective_locale_without_translation_file(self) -> None:
    self.assertEqual(locale_catalog.resolve_effective_locale("xx"), "en")

  # Verify resolve effective locale with translation file.
  def test_resolve_effective_locale_with_translation_file(self) -> None:
    self.assertEqual(locale_catalog.resolve_effective_locale("ru"), "ru")

  # Verify resolve effective locale english.
  def test_resolve_effective_locale_english(self) -> None:
    self.assertEqual(locale_catalog.resolve_effective_locale("en"), "en")

  # Verify translate known key.
  def test_translate_known_key(self) -> None:
    self.assertEqual(
      locale_catalog.translate("sidebar.newChat", locale="en"),
      "New Chat",
    )

  # Verify translate missing key returns key.
  def test_translate_missing_key_returns_key(self) -> None:
    self.assertEqual(
      locale_catalog.translate("missing.key.path", locale="en"),
      "missing.key.path",
    )

  # Verify translate interpolation.
  def test_translate_interpolation(self) -> None:
    text = locale_catalog.translate(
      "context.usageLabel",
      locale="en",
      percent=50,
      remaining=50,
      used="1 K",
      window="8 K",
    )
    self.assertIn("50%", text)
    self.assertIn("1 K", text)

  # Verify translate fallback kwarg.
  def test_translate_fallback_kwarg(self) -> None:
    self.assertEqual(
      locale_catalog.translate("missing", locale="en", fallback="Fallback"),
      "Fallback",
    )

  # Verify list available includes en.
  def test_list_available_includes_en(self) -> None:
    self.assertIn("en", locale_catalog.list_available_chat_locales())
