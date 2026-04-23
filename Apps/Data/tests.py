# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from API import mcp as tool_registry
from Apps.Data.lms_presets import (
    activate_lms_preset,
    create_lms_preset,
    delete_lms_preset,
    ensure_lms_preset_state,
    normalize_lms_preset_config,
    rename_lms_preset,
    sync_active_lms_preset,
)
from Apps.Data.models import (
    Chat,
    LmsPreset,
    Message,
    MessageAttachment,
    MessageAttachmentKind,
    MessageImage,
    MessageRole,
    OllamaPreset,
)
from Apps.Data.ollama_presets import (
    DEFAULT_OLLAMA_PRESET_CONFIG,
    activate_ollama_preset,
    create_ollama_preset,
    delete_ollama_preset,
    ensure_ollama_preset_state,
    normalize_ollama_preset_config,
    rename_ollama_preset,
    sync_active_ollama_preset,
)


# Shared test helpers.
# Provide isolated tool-registry fixtures for tests.
class ToolRegistryTestCase(TestCase):
    """Provide helpers for exercising local ``Tools/*/mcp-server.py`` discovery."""

    # Create an isolated tools directory.
    def setUp(self):
        super().setUp()
        self._tools_dir_context = tempfile.TemporaryDirectory()
        self.tools_dir = Path(self._tools_dir_context.name)
        self.tools_patch = patch.object(tool_registry, "TOOLS_DIR", self.tools_dir)
        self.tools_patch.start()
        tool_registry.reset_cache()

    # Restore the original registry state.
    def tearDown(self):
        tool_registry.reset_cache()
        self.tools_patch.stop()
        self._tools_dir_context.cleanup()
        super().tearDown()

    # Write a temporary MCP server module.
    def write_server(self, folder: str, body: str) -> None:
        server_dir = self.tools_dir / folder
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / "mcp-server.py").write_text(
            textwrap.dedent(body).strip() + "\n",
            encoding="utf-8",
        )
        tool_registry.reset_cache()


# Chat and attachment model tests.
# Verify compact model helpers used by admin and API serialization.
class ChatMessageModelTests(TestCase):
    """Verify string helpers on persisted chat data."""

    # Test chat and message string values stay readable.
    def test_chat_and_message_string_representations_are_readable(self):
        chat = Chat.objects.create(title="Planning")
        message = Message.objects.create(
            chat=chat,
            role=MessageRole.USER,
            content="x" * 60,
        )

        self.assertEqual(str(chat), "Planning")
        self.assertEqual(str(message), f"user: {'x' * 50}")


# Attachment model tests.
# Verify helper behavior for legacy image records.
class MessageImageTests(TestCase):
    """Verify helper serialization on stored message images."""

    # Ensure data URLs include the expected prefix.
    def test_data_url_builds_valid_prefix(self):
        chat = Chat.objects.create(title="Test")
        message = Message.objects.create(chat=chat, role=MessageRole.USER, content="Hello")
        image = MessageImage.objects.create(
            message=message,
            mime_type="image/png",
            data="abc123",
        )

        self.assertEqual(image.data_url(), "data:image/png;base64,abc123")


# Attachment model tests.
# Verify normalized attachment helpers and ordering.
class MessageAttachmentTests(TestCase):
    """Verify helper behavior for normalized message attachments."""

    # Set up a message for attachment records.
    def setUp(self):
        super().setUp()
        self.chat = Chat.objects.create(title="Test")
        self.message = Message.objects.create(
            chat=self.chat,
            role=MessageRole.USER,
            content="Hello",
        )

    # Ensure data URLs and image detection use stored metadata.
    def test_data_url_and_image_detection_use_stored_metadata(self):
        image = MessageAttachment.objects.create(
            message=self.message,
            kind=MessageAttachmentKind.FILE,
            name="diagram.svg",
            mime_type="image/svg+xml",
            data="PHN2Zz4=",
            size_bytes=6,
        )
        file_attachment = MessageAttachment.objects.create(
            message=self.message,
            kind=MessageAttachmentKind.FILE,
            name="note.txt",
            mime_type="text/plain",
            data="SGVsbG8=",
            size_bytes=5,
        )

        self.assertEqual(image.data_url(), "data:image/svg+xml;base64,PHN2Zz4=")
        self.assertTrue(image.is_image)
        self.assertFalse(file_attachment.is_image)

    # Ensure attachment query ordering is stable for the UI.
    def test_attachment_ordering_uses_order_then_id(self):
        last = MessageAttachment.objects.create(
            message=self.message,
            name="last.txt",
            data="MQ==",
            order=2,
        )
        first = MessageAttachment.objects.create(
            message=self.message,
            name="first.txt",
            data="Mg==",
            order=1,
        )
        second = MessageAttachment.objects.create(
            message=self.message,
            name="second.txt",
            data="Mw==",
            order=1,
        )

        self.assertEqual(list(self.message.attachments.all()), [first, second, last])
        self.assertEqual(str(first), f"first.txt for message {self.message.id}")


# Ollama preset tests.
# Verify the Ollama preset lifecycle for one model.
class OllamaPresetTests(TestCase):
    """Verify per-model Ollama preset lifecycle helpers."""

    # Create the default preset when no saved state exists.
    def test_ensure_state_creates_default_preset(self):
        presets, active_preset = ensure_ollama_preset_state("llama3")

        self.assertEqual(len(presets), 1)
        self.assertTrue(active_preset.is_default)
        self.assertTrue(active_preset.is_active)
        self.assertEqual(active_preset.config["num_ctx"], DEFAULT_OLLAMA_PRESET_CONFIG["num_ctx"])
        self.assertEqual(active_preset.config["num_predict"], DEFAULT_OLLAMA_PRESET_CONFIG["num_predict"])

    # Promote the default preset when saved state has no active preset.
    def test_ensure_state_promotes_default_when_no_active_preset_exists(self):
        default = OllamaPreset.objects.create(
            model_name="llama3",
            name="Default",
            config=DEFAULT_OLLAMA_PRESET_CONFIG,
            is_default=True,
            is_active=False,
        )
        OllamaPreset.objects.create(
            model_name="llama3",
            name="Custom",
            config={"num_ctx": 49152},
            is_default=False,
            is_active=False,
        )

        presets, active_preset = ensure_ollama_preset_state("llama3")

        self.assertEqual(active_preset.id, default.id)
        self.assertEqual(sum(1 for preset in presets if preset.is_active), 1)

    # Deactivate duplicate active presets to keep runtime state deterministic.
    def test_ensure_state_keeps_only_one_active_preset(self):
        OllamaPreset.objects.create(
            model_name="llama3",
            name="Default",
            config=DEFAULT_OLLAMA_PRESET_CONFIG,
            is_default=True,
            is_active=True,
        )
        duplicate = OllamaPreset.objects.create(
            model_name="llama3",
            name="Coding",
            config={"num_ctx": 49152},
            is_default=False,
            is_active=True,
        )

        presets, active_preset = ensure_ollama_preset_state("llama3")

        duplicate.refresh_from_db()
        self.assertTrue(active_preset.is_default)
        self.assertFalse(duplicate.is_active)
        self.assertEqual(sum(1 for preset in presets if preset.is_active), 1)

    # Clone the default preset when the active config changes.
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

    # Keep the default preset active when the config has not changed.
    def test_sync_unchanged_default_config_does_not_create_custom_preset(self):
        payload = sync_active_ollama_preset("llama3", DEFAULT_OLLAMA_PRESET_CONFIG)

        active = OllamaPreset.objects.get(id=payload["active_preset_id"])
        self.assertTrue(active.is_default)
        self.assertEqual(OllamaPreset.objects.filter(model_name="llama3").count(), 1)

    # Update custom active presets in place.
    def test_sync_custom_active_preset_updates_in_place(self):
        created = create_ollama_preset(
            "llama3",
            name="Coding",
            config={"num_ctx": 49152, "num_predict": 2048},
            activate=True,
        )

        payload = sync_active_ollama_preset(
            "llama3",
            {"num_ctx": 65536, "num_predict": 4096},
        )

        self.assertEqual(payload["active_preset_id"], created["active_preset_id"])
        self.assertEqual(OllamaPreset.objects.filter(model_name="llama3").count(), 1)
        active = OllamaPreset.objects.get(id=payload["active_preset_id"])
        self.assertEqual(active.config["num_ctx"], 65536)

    # Fall back to the default preset after deleting the active custom one.
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

    # Select a custom preset and deactivate the previous active one.
    def test_activate_preset_switches_active_record(self):
        default_payload = sync_active_ollama_preset("llama3", DEFAULT_OLLAMA_PRESET_CONFIG)
        custom = create_ollama_preset(
            "llama3",
            name="Coding",
            config={"num_ctx": 49152},
            activate=False,
        )
        custom_preset = OllamaPreset.objects.get(name="Coding")

        payload = activate_ollama_preset("llama3", str(custom_preset.id))

        self.assertEqual(payload["active_preset_id"], str(custom_preset.id))
        self.assertFalse(OllamaPreset.objects.get(id=default_payload["active_preset_id"]).is_active)
        self.assertTrue(OllamaPreset.objects.get(id=custom_preset.id).is_active)
        self.assertEqual(len(custom["presets"]), 2)

    # Reject unsafe operations against the default preset.
    def test_default_preset_cannot_be_renamed_or_deleted(self):
        presets, default_preset = ensure_ollama_preset_state("llama3")

        with self.assertRaisesMessage(ValueError, "default preset cannot be renamed"):
            rename_ollama_preset("llama3", str(default_preset.id), "Renamed")
        with self.assertRaisesMessage(ValueError, "default preset cannot be deleted"):
            delete_ollama_preset("llama3", str(default_preset.id))
        self.assertEqual(len(presets), 1)

    # Drop unsupported runtime keys before saving a preset.
    def test_sync_drops_unsupported_runtime_keys_from_preset_config(self):
        payload = sync_active_ollama_preset(
            "llama3",
            {
                "num_ctx": 65536,
                "think": True,
                "mirostat": 2,
                "numa": True,
                "vocab_only": True,
            },
        )

        active = OllamaPreset.objects.get(id=payload["active_preset_id"])
        self.assertEqual(active.config["num_ctx"], 65536)
        self.assertTrue(active.config["think"])
        self.assertNotIn("mirostat", active.config)
        self.assertNotIn("numa", active.config)
        self.assertNotIn("vocab_only", active.config)

    # Normalize compact configs and keep only supported runtime keys.
    def test_normalize_config_removes_empty_and_unsupported_values(self):
        payload = normalize_ollama_preset_config(
            {
                "num_ctx": 65536,
                "think": True,
                "stop": ["", "END"],
                "mirostat": 2,
                "nested": {"empty": ""},
            }
        )

        self.assertEqual(payload["num_ctx"], 65536)
        self.assertEqual(payload["stop"], ["END"])
        self.assertTrue(payload["think"])
        self.assertNotIn("mirostat", payload)
        self.assertNotIn("nested", payload)


# LM Studio preset tests.
# Verify the LM Studio preset lifecycle for one model.
class LmsPresetTests(TestCase):
    """Verify per-model LM Studio preset lifecycle helpers."""

    # Create the default preset from model defaults when no state exists.
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings")
    def test_ensure_state_creates_default_preset(self, mock_get_model_settings):
        mock_get_model_settings.return_value = {
            "defaults": {"temperature": 0.7, "think": True},
        }

        presets, active_preset = ensure_lms_preset_state("qwen3")

        self.assertEqual(len(presets), 1)
        self.assertTrue(active_preset.is_default)
        self.assertTrue(active_preset.is_active)
        self.assertEqual(active_preset.config["operation"]["temperature"], 0.7)

    # Promote the default preset when no preset is active.
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings")
    def test_ensure_state_promotes_default_when_no_active_preset_exists(self, mock_get_model_settings):
        mock_get_model_settings.return_value = {
            "defaults": {"temperature": 0.7},
        }
        default = LmsPreset.objects.create(
            model_name="qwen3",
            name="Default",
            config={"operation": {"temperature": 0.7}},
            is_default=True,
            is_active=False,
        )
        LmsPreset.objects.create(
            model_name="qwen3",
            name="Coding",
            config={"operation": {"temperature": 0.2}},
            is_default=False,
            is_active=False,
        )

        presets, active_preset = ensure_lms_preset_state("qwen3")

        self.assertEqual(active_preset.id, default.id)
        self.assertEqual(sum(1 for preset in presets if preset.is_active), 1)

    # Clone the default preset when the active config changes.
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings")
    def test_sync_from_default_creates_custom_active_preset(self, mock_get_model_settings):
        mock_get_model_settings.return_value = {
            "defaults": {"temperature": 0.7},
        }

        payload = sync_active_lms_preset(
            "qwen3",
            {
                "operation": {"temperature": 0.2, "think": False},
            },
        )

        self.assertEqual(LmsPreset.objects.filter(model_name="qwen3").count(), 2)
        active = LmsPreset.objects.get(id=payload["active_preset_id"])
        self.assertFalse(active.is_default)
        self.assertFalse(active.config["operation"]["think"])

    # Keep the default preset when the config matches model defaults.
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings")
    def test_sync_unchanged_default_config_does_not_create_custom_preset(self, mock_get_model_settings):
        mock_get_model_settings.return_value = {
            "defaults": {"temperature": 0.7},
        }

        payload = sync_active_lms_preset("qwen3", {"operation": {"temperature": 0.7}})

        active = LmsPreset.objects.get(id=payload["active_preset_id"])
        self.assertTrue(active.is_default)
        self.assertEqual(LmsPreset.objects.filter(model_name="qwen3").count(), 1)

    # Update a custom active preset in place.
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings")
    def test_sync_custom_active_preset_updates_in_place(self, mock_get_model_settings):
        mock_get_model_settings.return_value = {
            "defaults": {"temperature": 0.7},
        }
        created = create_lms_preset(
            "qwen3",
            name="Coding",
            config={"operation": {"temperature": 0.2}},
            activate=True,
        )

        payload = sync_active_lms_preset(
            "qwen3",
            {"operation": {"temperature": 0.4, "think": False}},
        )

        self.assertEqual(payload["active_preset_id"], created["active_preset_id"])
        self.assertEqual(LmsPreset.objects.filter(model_name="qwen3").count(), 1)
        active = LmsPreset.objects.get(id=payload["active_preset_id"])
        self.assertEqual(active.config["operation"]["temperature"], 0.4)

    # Fall back to the default preset after deleting the active custom one.
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings")
    def test_delete_active_custom_preset_falls_back_to_default(self, mock_get_model_settings):
        mock_get_model_settings.return_value = {
            "defaults": {"temperature": 0.7},
        }
        created = create_lms_preset(
            "qwen3",
            name="Coding",
            config={"operation": {"temperature": 0.2}},
            activate=True,
        )
        delete_lms_preset("qwen3", created["active_preset_id"])

        active = LmsPreset.objects.get(model_name="qwen3", is_active=True)
        self.assertTrue(active.is_default)

    # Select a custom preset and deactivate the previous active one.
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings")
    def test_activate_preset_switches_active_record(self, mock_get_model_settings):
        mock_get_model_settings.return_value = {
            "defaults": {"temperature": 0.7},
        }
        default_payload = sync_active_lms_preset("qwen3", {"operation": {"temperature": 0.7}})
        custom = create_lms_preset(
            "qwen3",
            name="Coding",
            config={"operation": {"temperature": 0.2}},
            activate=False,
        )
        custom_preset = LmsPreset.objects.get(name="Coding")

        payload = activate_lms_preset("qwen3", str(custom_preset.id))

        self.assertEqual(payload["active_preset_id"], str(custom_preset.id))
        self.assertFalse(LmsPreset.objects.get(id=default_payload["active_preset_id"]).is_active)
        self.assertTrue(LmsPreset.objects.get(id=custom_preset.id).is_active)
        self.assertEqual(len(custom["presets"]), 2)

    # Reject unsafe operations against the default preset.
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings")
    def test_default_preset_cannot_be_renamed_or_deleted(self, mock_get_model_settings):
        mock_get_model_settings.return_value = {
            "defaults": {"temperature": 0.7},
        }
        presets, default_preset = ensure_lms_preset_state("qwen3")

        with self.assertRaisesMessage(ValueError, "default preset cannot be renamed"):
            rename_lms_preset("qwen3", str(default_preset.id), "Renamed")
        with self.assertRaisesMessage(ValueError, "default preset cannot be deleted"):
            delete_lms_preset("qwen3", str(default_preset.id))
        self.assertEqual(len(presets), 1)

    # Normalize legacy top-level options into the operation block.
    def test_normalize_config_moves_top_level_options_into_operation(self):
        payload = normalize_lms_preset_config(
            {
                "temperature": 0.2,
                "stop": ["", "END"],
                "load": {"contextLength": 32768},
            }
        )

        self.assertEqual(payload, {"operation": {"temperature": 0.2, "stop": ["END"]}})


# Tool registry tests.
# Verify MCP-style local server discovery and execution.
class LocalServerRegistryTests(ToolRegistryTestCase):
    """Verify discovery and execution of local MCP-style server modules."""

    # Discover valid local server modules.
    def test_list_servers_discovers_valid_server_modules(self):
        self.write_server(
            "time_suite",
            """
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
            """,
        )

        payload = tool_registry.list_servers()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["id"], "time_suite")
        self.assertEqual(payload[0]["tool_count"], 2)
        self.assertEqual(payload[0]["tools"][0]["id"], "time_now")

    # Hide servers that do not support the requested engine.
    def test_supports_filter_hides_servers_for_unsupported_engines(self):
        self.write_server(
            "ollama_only",
            """
            MCP_SERVER = {"id": "ollama_only", "name": "Ollama Only"}
            TOOLS = [{"id": "echo", "name": "Echo", "parameters": {"type": "object", "properties": {}}}]

            def supports(engine=None, model_name=None):
                return engine == "ollama-service"

            def call_tool(tool_id, arguments, context=None):
                return "ok"
            """,
        )

        self.assertEqual(tool_registry.list_servers(engine="openai"), [])
        self.assertEqual(tool_registry.list_servers(engine="ollama-service")[0]["id"], "ollama_only")

    # Build one OpenAI-style tool entry per local server tool.
    def test_build_ollama_tools_registers_multiple_tools(self):
        self.write_server(
            "multi",
            """
            MCP_SERVER = {"id": "multi", "name": "Multi"}
            TOOLS = [
                {"id": "alpha", "name": "Alpha", "parameters": {"type": "object", "properties": {}}},
                {"id": "beta", "name": "Beta", "parameters": {"type": "object", "properties": {}}},
            ]

            def call_tool(tool_id, arguments, context=None):
                return {"tool_id": tool_id}
            """,
        )

        tools, lookup = tool_registry.build_ollama_tools("multi", engine="ollama-service", model_name="llama3")
        aliases = [tool["function"]["name"] for tool in tools]

        self.assertEqual(len(tools), 2)
        self.assertIn("multi__alpha", aliases)
        self.assertIn("multi__beta", aliases)
        self.assertIn("multi__alpha", lookup)
        self.assertEqual(lookup["multi__alpha"]["tool"]["id"], "alpha")

    # Pass context through tool execution and serialize the result.
    def test_call_ollama_tool_serializes_results_and_passes_context(self):
        self.write_server(
            "context_suite",
            """
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
            """,
        )

        tools, lookup = tool_registry.build_ollama_tools("context_suite", engine="ollama-service", model_name="llama3")
        self.assertEqual(len(tools), 1)

        payload = tool_registry.call_ollama_tool(
            lookup,
            "context_suite__context_echo",
            {"value": "hello"},
            context={"chat_id": "chat-1"},
        )

        self.assertIn('"tool_id": "context_echo"', payload)
        self.assertIn('"value": "hello"', payload)
        self.assertIn('"chat_id": "chat-1"', payload)
        self.assertIn('"server_name": "Context Suite"', payload)

    # Skip invalid local server modules without breaking discovery.
    def test_invalid_server_modules_are_skipped(self):
        self.write_server(
            "invalid",
            """
            MCP_SERVER = {"id": "invalid", "name": "Invalid"}
            TOOLS = [{"id": "echo", "name": "Echo", "parameters": {"type": "object", "properties": {}}}]
            """,
        )

        self.assertEqual(tool_registry.list_servers(), [])

    # Execute servers that expose dedicated tool handlers.
    def test_tool_handlers_are_supported_without_generic_dispatcher(self):
        self.write_server(
            "handler_suite",
            """
            MCP_SERVER = {"id": "handler_suite", "name": "Handler Suite"}
            TOOLS = [{"id": "echo", "name": "Echo", "parameters": {"type": "object", "properties": {}}}]

            def echo(arguments, context=None):
                return {
                    "value": arguments.get("value"),
                    "alias": context.get("tool_alias"),
                }

            TOOL_HANDLERS = {"echo": echo}
            """,
        )

        _tools, lookup = tool_registry.build_ollama_tools("handler_suite")
        payload = tool_registry.call_ollama_tool(
            lookup,
            "handler_suite__echo",
            {"value": "hello"},
        )

        self.assertIn('"value": "hello"', payload)
        self.assertIn('"alias": "handler_suite__echo"', payload)

    # Execute async tool handlers through the sync registry API.
    def test_async_tool_handlers_are_supported(self):
        self.write_server(
            "async_suite",
            """
            MCP_SERVER = {"id": "async_suite", "name": "Async Suite"}
            TOOLS = [{"id": "echo", "name": "Echo", "parameters": {"type": "object", "properties": {}}}]

            async def echo(arguments, context=None):
                return {"value": arguments.get("value")}

            TOOL_HANDLERS = {"echo": echo}
            """,
        )

        _tools, lookup = tool_registry.build_ollama_tools("async_suite")
        payload = tool_registry.call_ollama_tool(
            lookup,
            "async_suite__echo",
            {"value": "async"},
        )

        self.assertIn('"value": "async"', payload)

    # Return a readable error for unknown tool aliases.
    def test_call_ollama_tool_returns_error_for_unknown_alias(self):
        payload = tool_registry.call_ollama_tool({}, "missing__tool", {})

        self.assertEqual(payload, "Unknown tool: missing__tool")
