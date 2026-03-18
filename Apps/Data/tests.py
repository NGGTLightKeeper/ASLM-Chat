"""Tests for chat data models, presets, and local tool discovery."""

from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from API import mcp as tool_registry
from Apps.Data.models import Chat, Message, MessageImage, MessageRole, OllamaPreset
from Apps.Data.ollama_presets import (
    DEFAULT_OLLAMA_PRESET_CONFIG,
    create_ollama_preset,
    delete_ollama_preset,
    ensure_ollama_preset_state,
    sync_active_ollama_preset,
)


class ToolRegistryTestCase(TestCase):
    """Provide helpers for exercising local ``Tools/*/tool.py`` discovery."""

    def setUp(self):
        super().setUp()
        self._tools_dir_context = tempfile.TemporaryDirectory()
        self.tools_dir = Path(self._tools_dir_context.name)
        self.tools_patch = patch.object(tool_registry, 'TOOLS_DIR', self.tools_dir)
        self.tools_patch.start()
        tool_registry.reset_cache()

    def tearDown(self):
        tool_registry.reset_cache()
        self.tools_patch.stop()
        self._tools_dir_context.cleanup()
        super().tearDown()

    def write_tool(self, folder: str, body: str) -> None:
        tool_dir = self.tools_dir / folder
        tool_dir.mkdir(parents=True, exist_ok=True)
        (tool_dir / 'tool.py').write_text(textwrap.dedent(body).strip() + '\n', encoding='utf-8')
        tool_registry.reset_cache()


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


class LocalToolRegistryTests(ToolRegistryTestCase):
    """Verify discovery and execution of local ``tool.py`` modules."""

    def test_list_tools_discovers_valid_tool_modules(self):
        self.write_tool(
            'echo',
            '''
            TOOL = {
                "id": "echo",
                "name": "Echo",
                "description": "Echo text back to the model.",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            }

            def call_tool(arguments, context=None):
                return {"text": arguments.get("text", "")}
            ''',
        )

        self.assertEqual(
            tool_registry.list_tools(),
            [{"id": "echo", "name": "Echo", "description": "Echo text back to the model."}],
        )

    def test_supports_filter_hides_tools_for_unsupported_engines(self):
        self.write_tool(
            'ollama_only',
            '''
            TOOL = {"id": "ollama_only", "name": "Ollama Only", "parameters": {"type": "object", "properties": {}}}

            def supports(engine=None, model_name=None):
                return engine == "ollama-service"

            def call_tool(arguments, context=None):
                return "ok"
            ''',
        )

        self.assertEqual(tool_registry.list_tools(engine='openai'), [])
        self.assertEqual(tool_registry.list_tools(engine='ollama-service')[0]['id'], 'ollama_only')

    def test_call_ollama_tool_serializes_results_and_passes_context(self):
        self.write_tool(
            'context_echo',
            '''
            TOOL = {
                "id": "context_echo",
                "name": "Context Echo",
                "parameters": {"type": "object", "properties": {"value": {"type": "string"}}},
            }

            def call_tool(arguments, context=None):
                return {
                    "value": arguments.get("value"),
                    "chat_id": context.get("chat_id"),
                    "tool_name": context.get("tool_name"),
                }
            ''',
        )

        tools, lookup = tool_registry.build_ollama_tools('context_echo', engine='ollama-service', model_name='llama3')
        self.assertEqual(len(tools), 1)

        payload = tool_registry.call_ollama_tool(
            lookup,
            'context_echo',
            {'value': 'hello'},
            context={'chat_id': 'chat-1'},
        )

        self.assertIn('"value": "hello"', payload)
        self.assertIn('"chat_id": "chat-1"', payload)
        self.assertIn('"tool_name": "Context Echo"', payload)
