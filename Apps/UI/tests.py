"""Tests for ASLM-Chat UI helpers and endpoints."""

from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from API import llm_api
from API import mcp as tool_registry
from API.openai import _build_openai_request_options
from Apps.Data.models import Chat, OllamaPreset
from Apps.UI.views import _extract_model_name


class ToolRegistryTestMixin:
    """Patch the local tools directory for endpoint tests."""

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


class ModelNameExtractionTests(SimpleTestCase):
    """Cover adapter-specific model list formats."""

    def test_extracts_name_from_string(self):
        self.assertEqual(_extract_model_name("llama3"), "llama3")

    def test_extracts_name_from_mapping(self):
        self.assertEqual(_extract_model_name({"model": "qwen"}), "qwen")
        self.assertEqual(_extract_model_name({"name": "gpt-oss"}), "gpt-oss")
        self.assertEqual(_extract_model_name({"model_key": "mistral-nemo"}), "mistral-nemo")

    def test_prefers_id_over_friendly_name(self):
        self.assertEqual(
            _extract_model_name({"id": "openai/gpt-oss-20b", "name": "OpenAI: GPT OSS 20B"}),
            "openai/gpt-oss-20b",
        )


class MainViewTests(ToolRegistryTestMixin, TestCase):
    """Verify that the main page uses the configured engine and tool helpers."""

    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_main_view_includes_runtime_settings_and_local_tools(self, _mock_engine):
        self.write_tool(
            'echo',
            '''
            TOOL = {"id": "echo", "name": "Echo", "description": "Echo tool", "parameters": {"type": "object", "properties": {}}}
            def call_tool(arguments, context=None):
                return "ok"
            ''',
        )

        response = self.client.get(reverse("main"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["models"], [])
        self.assertEqual(response.context["llm_engine"], "ollama-service")
        self.assertIn("runtime_settings", response.context)
        self.assertEqual(response.context["available_tools"], [{"id": "echo", "name": "Echo", "description": "Echo tool"}])


class OpenAiOptionMappingTests(SimpleTestCase):
    """Ensure generic runtime options are safely mapped for OpenAI-compatible APIs."""

    def test_maps_supported_options_and_keeps_custom_values_in_extra_body(self):
        payload = _build_openai_request_options(
            {
                "temperature": 0.7,
                "num_predict": 256,
                "num_ctx": 4096,
                "top_k": 40,
            },
            think_level="high",
        )

        self.assertEqual(payload["temperature"], 0.7)
        self.assertEqual(payload["max_tokens"], 256)
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertEqual(payload["extra_body"]["num_ctx"], 4096)
        self.assertEqual(payload["extra_body"]["top_k"], 40)

    @patch("openai.OpenAI")
    @patch("API.openai.settings.get_engine_url", return_value="http://127.0.0.1:9000/v1")
    @patch("API.openai.settings.get_openai_api_key", return_value="")
    def test_openai_client_omits_api_key_when_not_configured(
        self,
        _mock_api_key,
        _mock_engine_url,
        mock_openai_client,
    ):
        from API.openai import _get_client

        mock_openai_client.return_value = Mock()
        _get_client()

        self.assertNotIn("api_key", mock_openai_client.call_args.kwargs)


class EngineRegistryTests(SimpleTestCase):
    """Cover generic engine registry behavior for optional capabilities."""

    def test_reload_model_raises_for_engines_without_reload_support(self):
        with self.assertRaises(NotImplementedError):
            llm_api.reload_model("openai", "gpt-oss")


class ChatApiTests(ToolRegistryTestMixin, TestCase):
    """Exercise chat API basics without calling a real model backend."""

    def setUp(self):
        super().setUp()
        self.client = Client()

    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_creates_new_chat_and_streams_response(
        self,
        _mock_engine,
        mock_generate,
        mock_prepare_runtime,
    ):
        mock_generate.return_value = [{"message": {"content": "Hi there"}}]

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"llama3"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.has_header("X-Chat-ID"))
        self.assertEqual(b"".join(response.streaming_content), b"Hi there")
        self.assertEqual(Chat.objects.count(), 1)
        self.assertEqual(Chat.objects.first().messages.count(), 2)
        mock_prepare_runtime.assert_called_once_with("ollama-service")

    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_passes_selected_tool_to_ollama(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
    ):
        self.write_tool(
            'echo',
            '''
            TOOL = {"id": "echo", "name": "Echo", "description": "Echo tool", "parameters": {"type": "object", "properties": {}}}
            def supports(engine=None, model_name=None):
                return engine == "ollama-service"
            def call_tool(arguments, context=None):
                return "ok"
            ''',
        )
        mock_generate.return_value = [{"message": {"content": "Done"}}]

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"llama3","tool_id":"echo"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'Done')
        self.assertEqual(mock_generate.call_args.kwargs["tool_id"], "echo")
        self.assertEqual(mock_generate.call_args.kwargs["tool_context"]["engine"], "ollama-service")
        self.assertEqual(Chat.objects.first().active_tool_slug, 'echo')

    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_rejects_unknown_tool(self, _mock_engine):
        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"llama3","tool_id":"missing"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown or unsupported tool", response.json()["error"])


class RuntimeSettingsApiTests(TestCase):
    """Verify runtime settings and dynamic model selection endpoints."""

    def test_get_runtime_settings_payload(self):
        response = self.client.get(reverse("runtime_settings_api"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("models", response.json())
        self.assertIn("lms_load_config", response.json())

    @patch("Apps.UI.views.llm_api.handle_engine_transition")
    def test_post_runtime_settings_updates_engine(self, mock_transition):
        response = self.client.post(
            reverse("runtime_settings_api"),
            data='{"llm-engine":"openai","openai_url":"http://127.0.0.1:9000/v1"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["llm-engine"], "openai")
        self.assertEqual(payload["openai_url"], "127.0.0.1:9000/v1")
        self.assertNotIn("models", payload)
        self.assertFalse(payload["has_openai_api_key"])
        mock_transition.assert_called_once()
        self.assertEqual(mock_transition.call_args.args[1], "openai")

    @patch("Apps.UI.views._load_models_for_engine", return_value=["llama3"])
    def test_models_api_returns_engine_specific_models(self, mock_models):
        response = self.client.get(reverse("models_api"), {"engine": "lms"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"engine": "lms", "models": ["llama3"]})
        mock_models.assert_called_once_with("lms")

    @patch("Apps.UI.views.llm_api.reload_model")
    def test_reload_model_api_reloads_selected_engine_model(self, mock_reload):
        response = self.client.post(
            reverse("reload_model_api"),
            data='{"engine":"lms","model":"qwen"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"engine": "lms", "model": "qwen", "reloaded": True})
        mock_reload.assert_called_once_with("lms", "qwen")

    @patch("Apps.UI.views.settings.get_supported_engines", return_value=[])
    @patch(
        "Apps.UI.views.settings.get_runtime_engine_settings",
        return_value={
            "llm-engine": "openai",
            "lms_url": "127.0.0.1:1234",
            "openai_url": "openrouter.ai/api/v1",
            "has_openai_api_key": True,
            "engine_urls": {"openai": "https://openrouter.ai/api/v1"},
        },
    )
    def test_runtime_settings_payload_does_not_expose_api_key(
        self,
        _mock_runtime_settings,
        _mock_engines,
    ):
        response = self.client.get(reverse("runtime_settings_api"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["has_openai_api_key"])
        self.assertNotIn("openai_api_key", payload)


class ToolApiTests(ToolRegistryTestMixin, TestCase):
    """Cover local tool listing and chat persistence endpoints."""

    def test_tools_api_returns_discovered_tools(self):
        self.write_tool(
            'echo',
            '''
            TOOL = {"id": "echo", "name": "Echo", "description": "Echo tool", "parameters": {"type": "object", "properties": {}}}
            def call_tool(arguments, context=None):
                return "ok"
            ''',
        )

        response = self.client.get(reverse("tools_api"), {"engine": "ollama-service", "model": "llama3"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tools"], [{"id": "echo", "name": "Echo", "description": "Echo tool"}])

    def test_load_chat_api_returns_active_tool_id(self):
        chat = Chat.objects.create(title="Chat", active_tool_slug="echo")

        response = self.client.get(reverse("load_chat_api", args=[chat.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["active_tool_id"], "echo")


class OllamaPresetApiTests(ToolRegistryTestMixin, TestCase):
    """Cover Ollama preset API endpoints and model-info integration."""

    @patch("Apps.UI.views.llm_api.get_model_settings")
    def test_model_info_includes_active_ollama_preset_defaults_and_tools(self, mock_get_model_settings):
        self.write_tool(
            'echo',
            '''
            TOOL = {"id": "echo", "name": "Echo", "description": "Echo tool", "parameters": {"type": "object", "properties": {}}}
            def supports(engine=None, model_name=None):
                return engine == "ollama-service"
            def call_tool(arguments, context=None):
                return "ok"
            ''',
        )
        mock_get_model_settings.return_value = {
            "modelinfo": {"general.architecture.context_length": 131072},
            "parameters": "temperature 0.8",
            "template": "",
            "capabilities": ["tools"],
        }

        response = self.client.get(
            reverse("model_info_api"),
            {"engine": "ollama-service", "model": "llama3"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("ollama_presets", payload)
        self.assertTrue(payload["supports_tool_calling"])
        self.assertEqual(payload["available_tools"], [{"id": "echo", "name": "Echo", "description": "Echo tool"}])
        self.assertEqual(payload["defaults"]["num_ctx"], 32768)
        self.assertEqual(payload["defaults"]["num_predict"], 8192)

    def test_sync_endpoint_clones_default_preset_on_first_change(self):
        response = self.client.post(
            reverse("sync_ollama_preset_api"),
            data='{"model":"llama3","config":{"num_ctx":65536,"num_predict":4096,"think":true,"think_level":"high"}}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["presets"]), 2)
        self.assertEqual(OllamaPreset.objects.filter(model_name="llama3").count(), 2)

    def test_create_rename_delete_endpoints_manage_custom_preset(self):
        created = self.client.post(
            reverse("create_ollama_preset_api"),
            data='{"model":"llama3","name":"Research","config":{"num_ctx":49152}}',
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 200)
        created_payload = created.json()
        active_preset_id = created_payload["active_preset_id"]

        renamed = self.client.post(
            reverse("rename_ollama_preset_api"),
            data=f'{{"model":"llama3","preset_id":"{active_preset_id}","name":"Research v2"}}',
            content_type="application/json",
        )
        self.assertEqual(renamed.status_code, 200)

        deleted = self.client.post(
            reverse("delete_ollama_preset_api"),
            data=f'{{"model":"llama3","preset_id":"{active_preset_id}"}}',
            content_type="application/json",
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(OllamaPreset.objects.filter(model_name="llama3").count(), 1)

    def test_duplicate_preset_name_returns_validation_error(self):
        self.client.post(
            reverse("create_ollama_preset_api"),
            data='{"model":"llama3","name":"Research","config":{"num_ctx":49152}}',
            content_type="application/json",
        )

        duplicate = self.client.post(
            reverse("create_ollama_preset_api"),
            data='{"model":"llama3","name":"Research","config":{"num_ctx":32768}}',
            content_type="application/json",
        )

        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("already exists", duplicate.json()["error"])

    def test_reload_api_returns_not_implemented_for_unsupported_engine(self):
        response = self.client.post(
            reverse("reload_model_api"),
            data='{"engine":"openai","model":"gpt-oss"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 501)
