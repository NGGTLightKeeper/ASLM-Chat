"""Tests for chat data models, presets, and local MCP-style server discovery."""

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
    """Provide helpers for exercising local ``Tools/*/mcp-server.py`` discovery."""

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

    def write_server(self, folder: str, body: str) -> None:
        server_dir = self.tools_dir / folder
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / 'mcp-server.py').write_text(
            textwrap.dedent(body).strip() + "\n",
            encoding='utf-8',
        )
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


class LocalServerRegistryTests(ToolRegistryTestCase):
    """Verify discovery and execution of local MCP-style server modules."""

    def test_list_servers_discovers_valid_server_modules(self):
        self.write_server(
            'time_suite',
            '''
            MCP_SERVER = {
                "id": "time_suite",
                "name": "Time Suite",
                "description": "Time helpers",
            }

            TOOLS = [
                {
                    "id": "time_now",
                    "name": "Current Time",
                    "description": "Return the current time.",
                    "parameters": {"type": "object", "properties": {}},
                },
                {
                    "id": "timezone_name",
                    "name": "Timezone Name",
                    "description": "Return the active timezone name.",
                    "parameters": {"type": "object", "properties": {}},
                },
            ]

            def call_tool(tool_id, arguments, context=None):
                return {"tool_id": tool_id}
            ''',
        )

        payload = tool_registry.list_servers()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["id"], "time_suite")
        self.assertEqual(payload[0]["tool_count"], 2)
        self.assertEqual(payload[0]["tools"][0]["id"], "time_now")

    def test_supports_filter_hides_servers_for_unsupported_engines(self):
        self.write_server(
            'ollama_only',
            '''
            MCP_SERVER = {"id": "ollama_only", "name": "Ollama Only"}
            TOOLS = [{"id": "echo", "name": "Echo", "parameters": {"type": "object", "properties": {}}}]

            def supports(engine=None, model_name=None):
                return engine == "ollama-service"

            def call_tool(tool_id, arguments, context=None):
                return "ok"
            ''',
        )

        self.assertEqual(tool_registry.list_servers(engine='openai'), [])
        self.assertEqual(tool_registry.list_servers(engine='ollama-service')[0]['id'], 'ollama_only')

    def test_build_ollama_tools_registers_multiple_tools(self):
        self.write_server(
            'multi',
            '''
            MCP_SERVER = {"id": "multi", "name": "Multi"}
            TOOLS = [
                {"id": "alpha", "name": "Alpha", "parameters": {"type": "object", "properties": {}}},
                {"id": "beta", "name": "Beta", "parameters": {"type": "object", "properties": {}}},
            ]

            def call_tool(tool_id, arguments, context=None):
                return {"tool_id": tool_id}
            ''',
        )

        tools, lookup = tool_registry.build_ollama_tools('multi', engine='ollama-service', model_name='llama3')
        aliases = [tool['function']['name'] for tool in tools]

        self.assertEqual(len(tools), 2)
        self.assertIn('multi__alpha', aliases)
        self.assertIn('multi__beta', aliases)
        self.assertIn('multi__alpha', lookup)
        self.assertEqual(lookup['multi__alpha']['tool']['id'], 'alpha')

    def test_call_ollama_tool_serializes_results_and_passes_context(self):
        self.write_server(
            'context_suite',
            '''
            MCP_SERVER = {"id": "context_suite", "name": "Context Suite"}
            TOOLS = [{
                "id": "context_echo",
                "name": "Context Echo",
                "parameters": {"type": "object", "properties": {"value": {"type": "string"}}},
            }]

            def call_tool(tool_id, arguments, context=None):
                return {
                    "tool_id": tool_id,
                    "value": arguments.get("value"),
                    "chat_id": context.get("chat_id"),
                    "server_name": context.get("server_name"),
                }
            ''',
        )

        tools, lookup = tool_registry.build_ollama_tools('context_suite', engine='ollama-service', model_name='llama3')
        self.assertEqual(len(tools), 1)

        payload = tool_registry.call_ollama_tool(
            lookup,
            'context_suite__context_echo',
            {'value': 'hello'},
            context={'chat_id': 'chat-1'},
        )

        self.assertIn('"tool_id": "context_echo"', payload)
        self.assertIn('"value": "hello"', payload)
        self.assertIn('"chat_id": "chat-1"', payload)
        self.assertIn('"server_name": "Context Suite"', payload)
