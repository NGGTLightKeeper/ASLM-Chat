"""Tests for chat data models."""

from __future__ import annotations

from django.test import TestCase

from Apps.Data.models import Chat, Message, MessageImage, MessageRole, OllamaPreset
from Apps.Data.ollama_presets import (
    DEFAULT_OLLAMA_PRESET_CONFIG,
    create_ollama_preset,
    delete_ollama_preset,
    ensure_ollama_preset_state,
    sync_active_ollama_preset,
)


class MessageImageTests(TestCase):
    """Verify helper serialization on stored message images."""

    def test_data_url_builds_valid_prefix(self):
        chat = Chat.objects.create(title="Test")
        message = Message.objects.create(chat=chat, role=MessageRole.USER, content="Hello")
        image = MessageImage.objects.create(
            message=message,
            mime_type="image/png",
            data="abc123",
        )

        self.assertEqual(image.data_url(), "data:image/png;base64,abc123")


class OllamaPresetTests(TestCase):
    """Verify per-model Ollama preset lifecycle helpers."""

    def test_ensure_state_creates_default_preset(self):
        presets, active_preset = ensure_ollama_preset_state("llama3")

        self.assertEqual(len(presets), 1)
        self.assertTrue(active_preset.is_default)
        self.assertTrue(active_preset.is_active)
        self.assertEqual(active_preset.config["num_ctx"], DEFAULT_OLLAMA_PRESET_CONFIG["num_ctx"])
        self.assertEqual(active_preset.config["num_predict"], DEFAULT_OLLAMA_PRESET_CONFIG["num_predict"])

    def test_sync_from_default_creates_custom_active_preset(self):
        payload = sync_active_ollama_preset(
            "llama3",
            {
                "num_ctx": 65536,
                "num_predict": 4096,
                "think": True,
                "think_level": "high",
            },
        )

        self.assertEqual(OllamaPreset.objects.filter(model_name="llama3").count(), 2)
        active = OllamaPreset.objects.get(id=payload["active_preset_id"])
        self.assertFalse(active.is_default)
        self.assertEqual(active.config["num_ctx"], 65536)
        self.assertEqual(active.config["think_level"], "high")

    def test_delete_active_custom_preset_falls_back_to_default(self):
        created = create_ollama_preset(
            "llama3",
            name="Coding",
            config={"num_ctx": 49152, "num_predict": 4096},
            activate=True,
        )
        delete_ollama_preset("llama3", created["active_preset_id"])

        active = OllamaPreset.objects.get(model_name="llama3", is_active=True)
        self.assertTrue(active.is_default)
