# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import json
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from API import google_genai as google_genai_api
from API import llm_api
from API import mcp as tool_registry
from API.google_genai import (
    generate as generate_google_genai,
    get_model_settings as get_google_genai_model_settings,
    get_models as get_google_genai_models,
)
from API.lms import (
    _prepare_openai_prediction_options,
    _serialize_model_info,
    get_model_settings as get_lms_model_settings,
)
from API.ollama import _prepare_chat_kwargs, prepare_runtime as prepare_ollama_runtime
from API.openai import (
    _build_openai_request_options,
    generate as generate_openai,
    get_model_settings as get_openai_model_settings,
)
from Apps.Data.models import Chat, LmsPreset, Message, MessageAttachment, OllamaPreset
from Apps.UI.views import (
    _clear_model_metadata_caches,
    _extract_ollama_model_info,
    _extract_model_name,
    _format_runtime_error,
    _normalize_request_attachments,
    _strip_llm_control_tokens,
)


# Small structured error helper for Google GenAI adapter tests.
class FakeGoogleError(Exception):
    """Small structured error helper for Google GenAI adapter tests."""

    # Initialize the instance.
    def __init__(
        self,
        code: int,
        status: str,
        message: str,
        *,
        details: list[dict[str, object]] | None = None,
    ) -> None:
        self.code = code
        self.status = status
        self.message = message
        self.details = {
            "error": {
                "code": code,
                "status": status,
                "message": message,
                "details": details or [],
            }
        }
        super().__init__(f"{code} {status}. {self.details}")


# Shared test helpers.

# Patch the local tools directory for endpoint tests.
class ToolRegistryTestMixin:
    """Patch the local tools directory for endpoint tests."""

    # Create an isolated tools directory.
    def setUp(self):
        super().setUp()
        self._tools_dir_context = tempfile.TemporaryDirectory()
        self.tools_dir = Path(self._tools_dir_context.name)
        self.tools_patch = patch.object(tool_registry, "TOOLS_DIR", self.tools_dir)
        self.tools_patch.start()
        tool_registry.reset_cache()
        _clear_model_metadata_caches()

    # Restore the original registry state.
    def tearDown(self):
        tool_registry.reset_cache()
        _clear_model_metadata_caches()
        self.tools_patch.stop()
        self._tools_dir_context.cleanup()
        super().tearDown()

    # Write a temporary MCP server.
    def write_server(self, folder: str, body: str) -> None:
        server_dir = self.tools_dir / folder
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / "mcp-server.py").write_text(
            textwrap.dedent(body).strip() + "\n",
            encoding="utf-8",
        )
        tool_registry.reset_cache()

# Model and adapter parsing tests.

# Cover adapter-specific model list formats.
class ModelNameExtractionTests(SimpleTestCase):
    """Cover adapter-specific model list formats."""

    # Test extracts name from string.
    def test_extracts_name_from_string(self):
        self.assertEqual(_extract_model_name("llama3"), "llama3")

    # Test extracts name from mapping.
    def test_extracts_name_from_mapping(self):
        self.assertEqual(_extract_model_name({"model": "qwen"}), "qwen")
        self.assertEqual(_extract_model_name({"name": "gpt-oss"}), "gpt-oss")
        self.assertEqual(_extract_model_name({"model_key": "mistral-nemo"}), "mistral-nemo")

    # Test prefers id over friendly name.
    def test_prefers_id_over_friendly_name(self):
        self.assertEqual(
            _extract_model_name({"id": "openai/gpt-oss-20b", "name": "OpenAI: GPT OSS 20B"}),
            "openai/gpt-oss-20b",
        )


# Attachment normalization tests.

# Cover fast attachment validation helpers.
class AttachmentNormalizationTests(SimpleTestCase):
    """Cover fast attachment validation helpers."""

    # Test invalid base64 attachments are ignored before persistence.
    def test_invalid_base64_attachments_are_ignored(self):
        self.assertEqual(
            _normalize_request_attachments({
                "attachments": [{"name": "bad.txt", "mime_type": "text/plain", "data": "not valid !!!"}],
            }),
            [],
        )


# View and runtime mapping tests.

# Verify that the main page uses the configured engine and local server helpers.
class MainViewTests(ToolRegistryTestMixin, TestCase):
    """Verify that the main page uses the configured engine and local server helpers."""

    # Test main view includes runtime settings and local servers.
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_main_view_includes_runtime_settings_and_local_servers(self, _mock_engine):
        self.write_server(
            'time_suite',
            '''
            MCP_SERVER = {"id": "time_suite", "name": "Time Suite", "description": "Time helpers"}
            TOOLS = [{"id": "time_now", "name": "Current Time", "parameters": {"type": "object", "properties": {}}}]
            def call_tool(tool_id, arguments, context=None):
                return "ok"
            ''',
        )

        response = self.client.get(reverse("main"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["models"], [])
        self.assertEqual(response.context["llm_engine"], "ollama-service")
        self.assertIn("runtime_settings", response.context)
        self.assertEqual(
            response.context["available_tool_servers"],
            [{
                "id": "time_suite",
                "name": "Time Suite",
                "description": "Time helpers",
                "tool_count": 1,
                "tools": [{"id": "time_now", "name": "Current Time", "description": ""}],
            }],
        )
        self.assertContains(response, 'id="group-load"')


# Ensure Ollama-only thinking parameters are normalized before request dispatch.
class OllamaOptionMappingTests(SimpleTestCase):
    """Ensure Ollama-only thinking parameters are normalized before request dispatch."""

    # Test prepare chat kwargs maps think level into think.
    def test_prepare_chat_kwargs_maps_think_level_into_think(self):
        payload = _prepare_chat_kwargs(
            {
                "stream": True,
                "think": True,
                "think_level": "high",
                "options": {"temperature": 0.7},
            }
        )

        self.assertNotIn("think_level", payload)
        self.assertEqual(payload["think"], "high")
        self.assertEqual(payload["options"]["temperature"], 0.7)

    # Test prepare chat kwargs drops runtime options unsupported by current Ollama.
    def test_prepare_chat_kwargs_drops_runtime_options_unsupported_by_current_ollama(self):
        payload = _prepare_chat_kwargs(
            {
                "options": {
                    "temperature": 0.7,
                    "num_ctx": 32768,
                    "mirostat": 2,
                    "numa": False,
                    "tfs_z": 1.0,
                }
            }
        )

        self.assertEqual(payload["options"]["temperature"], 0.7)
        self.assertEqual(payload["options"]["num_ctx"], 32768)
        self.assertNotIn("mirostat", payload["options"])
        self.assertNotIn("numa", payload["options"])
        self.assertNotIn("tfs_z", payload["options"])

    # Test prepare chat kwargs ignores LM Studio only internal keys.
    def test_prepare_chat_kwargs_ignores_lms_only_internal_keys(self):
        payload = _prepare_chat_kwargs(
            {
                "stream": True,
                "think": True,
                "think_param_name": "ext.virtualModel.customField.qwen.enableThinking",
                "think_level_param_name": "ext.virtualModel.customField.openai.reasoningEffort",
                "load_config": {"contextLength": 32768},
                "sync_operation_defaults": {"ext.virtualModel.customField.qwen.enableThinking": False},
                "options": {"temperature": 0.7},
            }
        )

        self.assertNotIn("think_param_name", payload)
        self.assertNotIn("think_level_param_name", payload)
        self.assertNotIn("load_config", payload)
        self.assertNotIn("sync_operation_defaults", payload)
        self.assertEqual(payload["think"], True)
        self.assertEqual(payload["options"]["temperature"], 0.7)

    # Test prepare runtime passes requested engine to managed service.
    @patch("API.ollama._get_ollama_service_module")
    def test_prepare_runtime_passes_requested_engine_to_managed_service(self, mock_get_service):
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        prepare_ollama_runtime("ollama-service")

        mock_service.start_ollama.assert_called_once_with(engine="ollama-service")


# Ensure Ollama tool support follows Ollama model metadata.
class OllamaModelInfoTests(SimpleTestCase):
    """Ensure Ollama model metadata maps tool support without model-name hardcoding."""

    # Test an explicit Ollama capabilities list without tools disables tool support.
    def test_ollama_capabilities_without_tools_disable_tool_support(self):
        payload = _extract_ollama_model_info({
            "capabilities": ["completion"],
            "template": "{{ if .Tools }}tools{{ end }}{{ if .ToolCalls }}calls{{ end }}",
        })

        self.assertFalse(payload["supports_tool_calling"])

    # Test Ollama's tools capability enables support without template markers.
    def test_ollama_tools_capability_enables_tool_support(self):
        payload = _extract_ollama_model_info({
            "capabilities": ["completion", "tools"],
            "template": "{{ if .Messages }}{{ end }}",
        })

        self.assertTrue(payload["supports_tool_calling"])

    # Test old/custom Ollama responses can still infer tools from the template.
    def test_ollama_tool_template_fallback_when_capabilities_are_missing(self):
        payload = _extract_ollama_model_info({
            "template": "{{ if .Messages }}{{ end }}",
        })

        self.assertFalse(payload["supports_tool_calling"])

        payload = _extract_ollama_model_info({
            "template": "{{ if .Tools }}tools{{ end }}{{ if .ToolCalls }}calls{{ end }}",
        })

        self.assertTrue(payload["supports_tool_calling"])


# Ensure generic runtime options are safely mapped for OpenAI-compatible APIs.
class OpenAiOptionMappingTests(SimpleTestCase):
    """Ensure generic runtime options are safely mapped for OpenAI-compatible APIs."""

    # Test maps supported options and keeps custom values in extra body.
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

    # Test OpenAI client uses placeholder API key when not configured.
    @patch("openai.OpenAI")
    @patch("API.openai.settings.get_engine_url", return_value="http://127.0.0.1:9000/v1")
    @patch("API.openai.settings.get_openai_api_key", return_value="")
    def test_openai_client_uses_placeholder_api_key_when_not_configured(
        self,
        _mock_api_key,
        _mock_engine_url,
        mock_openai_client,
    ):
        from API.openai import _get_client

        mock_openai_client.return_value = Mock()
        _get_client()

        self.assertEqual(mock_openai_client.call_args.kwargs["api_key"], "not-needed")


# Cover extended OpenAI-compatible capability parsing and reasoning output.
class OpenAiAdapterTests(SimpleTestCase):
    """Cover extended OpenAI-compatible capability parsing and reasoning output."""

    # Test get model settings reads OpenAI capabilities and reasoning.
    @patch("API.openai._get_client")
    def test_get_model_settings_reads_openai_capabilities_and_reasoning(self, mock_get_client):
        client = Mock()
        client.models.list.return_value = Mock(
            data=[
                {
                    "id": "gpt-test",
                    "capabilities": {"tools": True, "vision": True},
                    "reasoning": {
                        "enabled": True,
                        "effort": {
                            "default": "high",
                            "options": ["low", "medium", "high"],
                        },
                    },
                    "context_length": 65536,
                }
            ]
        )
        client.models.retrieve.return_value = {
            "id": "gpt-test",
            "supported_parameters": {
                "tools": {"type": "array"},
                "tool_choice": {"type": "string"},
                "reasoning_effort": {"enum": ["low", "medium", "high"]},
            },
            "defaults": {"temperature": 0.2},
        }
        mock_get_client.return_value = client

        payload = get_openai_model_settings("gpt-test")

        self.assertTrue(payload["supports_tool_calling"])
        self.assertTrue(payload["supports_vision"])
        self.assertTrue(payload["supports_thinking"])
        self.assertTrue(payload["supports_think_toggle"])
        self.assertTrue(payload["supports_think_level"])
        self.assertTrue(payload["supports_files"])
        self.assertEqual(payload["think_level_param_name"], "reasoning_effort")
        self.assertEqual(payload["defaults"]["temperature"], 0.2)
        self.assertEqual(payload["defaults"]["reasoning_effort"], "high")
        self.assertEqual(payload["think_level_options"], ["low", "medium", "high"])
        self.assertEqual(payload["context_length"], 65536)
        self.assertIn("tool_choice", payload["supported_parameters"])

    # Test get model settings reads direct feature flags and scalar supported parameters.
    @patch("API.openai._get_client")
    def test_get_model_settings_reads_direct_feature_flags_and_scalar_supported_parameters(self, mock_get_client):
        client = Mock()
        client.models.list.return_value = Mock(
            data=[
                {
                    "id": "gpt-test",
                    "vision": True,
                    "tool_calling": True,
                    "reasoning": True,
                    "input_modalities": ["text", "image"],
                }
            ]
        )
        client.models.retrieve.return_value = {
            "id": "gpt-test",
            "supported_parameters": ["temperature", "tools", "tool_choice", "reasoning_effort"],
        }
        mock_get_client.return_value = client

        payload = get_openai_model_settings("gpt-test")

        self.assertTrue(payload["supports_tool_calling"])
        self.assertTrue(payload["supports_vision"])
        self.assertTrue(payload["supports_thinking"])
        self.assertTrue(payload["supports_think_level"])
        self.assertFalse(payload["supports_think_toggle"])
        self.assertIn("reasoning_effort", payload["supported_parameters"])

    # Test generate stream parses reasoning and visible content.
    @patch("API.openai._get_client")
    def test_generate_stream_parses_reasoning_and_visible_content(self, mock_get_client):
        client = Mock()
        client.chat.completions.create.return_value = [
            {"choices": [{"delta": {"reasoning_content": "Plan first."}}]},
            {"choices": [{"delta": {"content": "Final answer"}}]},
        ]
        mock_get_client.return_value = client

        chunks = list(
            generate_openai(
                "gpt-test",
                [{"role": "user", "content": "Hi"}],
                stream=True,
            )
        )

        self.assertEqual(chunks[0]["message"]["thinking"], "Plan first.")
        self.assertEqual(chunks[0]["message"]["content"], "")
        self.assertEqual(chunks[1]["message"]["content"], "Final answer")

    # Test generate stream does not duplicate plain content into thinking.
    @patch("API.openai._get_client")
    def test_generate_stream_does_not_duplicate_plain_content_into_thinking(self, mock_get_client):
        client = Mock()
        client.chat.completions.create.return_value = [
            {"choices": [{"delta": {"content": "Hello"}}]},
            {"choices": [{"delta": {"content": " world"}}]},
        ]
        mock_get_client.return_value = client

        chunks = list(
            generate_openai(
                "gpt-test",
                [{"role": "user", "content": "Hi"}],
                stream=True,
            )
        )

        self.assertEqual([chunk["message"]["content"] for chunk in chunks], ["Hello", " world"])
        self.assertTrue(all("thinking" not in chunk["message"] for chunk in chunks))

    # Test get model settings reads companion metadata without generation.
    @patch("API.openai._get_companion_model_payload")
    @patch("API.openai._get_client")
    def test_get_model_settings_reads_companion_metadata_without_generation(
        self,
        mock_get_client,
        mock_get_companion_payload,
    ):
        client = Mock()
        client.models.list.return_value = Mock(data=[{"id": "gpt-probe", "object": "model", "owned_by": "org"}])
        client.models.retrieve.return_value = {"id": "gpt-probe", "object": "model", "owned_by": "org"}
        mock_get_companion_payload.return_value = {
            "key": "gpt-probe",
            "type": "llm",
            "max_context_length": 131072,
            "capabilities": {
                "vision": True,
                "trained_for_tool_use": True,
                "reasoning": {
                    "allowed_options": ["off", "on"],
                    "default": "on",
                },
            },
        }
        mock_get_client.return_value = client

        payload = get_openai_model_settings("gpt-probe")

        self.assertTrue(payload["supports_tool_calling"])
        self.assertTrue(payload["supports_thinking"])
        self.assertTrue(payload["supports_vision"])
        self.assertFalse(payload["supports_think_level"])
        self.assertTrue(payload["supports_think_toggle"])
        self.assertEqual(payload["think_level_options"], [])
        self.assertEqual(payload["defaults"]["think"], True)
        self.assertIn("tool_choice", payload["supported_parameters"])
        self.assertIn("tools", payload["supported_parameters"])
        client.chat.completions.create.assert_not_called()


# Cover Google GenAI filtering, capability learning, and thinking fallback.
class GoogleGenAiAdapterTests(SimpleTestCase):
    """Cover Google GenAI filtering, capability learning, and thinking fallback."""

    # Set up the test fixture.
    def setUp(self):
        super().setUp()
        google_genai_api._reset_runtime_caches()

    # Tear down the test fixture.
    def tearDown(self):
        google_genai_api._reset_runtime_caches()
        super().tearDown()

    # Test get models filters out non generate content models.
    @patch("API.google_genai._close_client")
    @patch("API.google_genai._get_client")
    def test_get_models_filters_out_non_generate_content_models(self, mock_get_client, _mock_close_client):
        client = Mock()
        payloads = [
            {"name": "models/gemini-2.5-flash", "supported_actions": ["generateContent"]},
            {"name": "models/veo-3.0-generate-001", "supported_actions": ["generateVideos"]},
        ]
        client.models.list.side_effect = lambda config=None: payloads
        mock_get_client.return_value = client

        models = get_google_genai_models()

        self.assertEqual([entry["model"] for entry in models], ["gemini-2.5-flash"])
        client.models.generate_content.assert_not_called()

    # Test get models hides zero quota models for current key after runtime learning.
    @patch("API.google_genai._close_client")
    @patch("API.google_genai._get_client")
    @patch("API.google_genai.settings.get_engine_url", return_value="https://generativelanguage.googleapis.com")
    @patch("API.google_genai.settings.get_google_genai_api_key", return_value="key-a")
    def test_get_models_hides_zero_quota_models_for_current_key_after_runtime_learning(
        self,
        _mock_api_key,
        _mock_engine_url,
        mock_get_client,
        _mock_close_client,
    ):
        client = Mock()
        payloads = [{"name": "models/gemini-3.1-pro", "supported_actions": ["generateContent"]}]
        client.models.list.side_effect = lambda config=None: payloads
        client.models.generate_content.side_effect = FakeGoogleError(
            429,
            "RESOURCE_EXHAUSTED",
            "Quota exceeded for model gemini-3.1-pro. limit: 0.",
            details=[{"violations": [{"quotaDimensions": {"model": "gemini-3.1-pro"}}]}],
        )
        mock_get_client.return_value = client

        with self.assertRaises(FakeGoogleError):
            list(
                generate_google_genai(
                    "gemini-3.1-pro",
                    [{"role": "user", "content": "Hi"}],
                    stream=False,
                )
            )

        self.assertEqual(get_google_genai_models(), [])
        self.assertEqual(client.models.generate_content.call_count, 1)

    # Test get models keeps temporarily rate limited models visible.
    @patch("API.google_genai._close_client")
    @patch("API.google_genai._get_client")
    @patch("API.google_genai.settings.get_engine_url", return_value="https://generativelanguage.googleapis.com")
    @patch("API.google_genai.settings.get_google_genai_api_key", return_value="key-a")
    def test_get_models_keeps_temporarily_rate_limited_models_visible(
        self,
        _mock_api_key,
        _mock_engine_url,
        mock_get_client,
        _mock_close_client,
    ):
        client = Mock()
        payloads = [{"name": "models/gemini-2.5-pro", "supported_actions": ["generateContent"]}]
        client.models.list.side_effect = lambda config=None: payloads
        client.models.generate_content.side_effect = FakeGoogleError(
            429,
            "RESOURCE_EXHAUSTED",
            "Quota exceeded for model gemini-2.5-pro. limit: 8. Please retry later.",
            details=[{"violations": [{"quotaDimensions": {"model": "gemini-2.5-pro"}}]}],
        )
        mock_get_client.return_value = client

        with self.assertRaises(FakeGoogleError):
            list(
                generate_google_genai(
                    "gemini-2.5-pro",
                    [{"role": "user", "content": "Hi"}],
                    stream=False,
                )
            )

        models = get_google_genai_models()
        cached_models = get_google_genai_models()

        self.assertEqual([entry["model"] for entry in models], ["gemini-2.5-pro"])
        self.assertEqual([entry["model"] for entry in cached_models], ["gemini-2.5-pro"])
        self.assertEqual(client.models.generate_content.call_count, 1)

    # Test get model settings returns toggle when thinking level is unsupported.
    @patch("API.google_genai._close_client")
    @patch("API.google_genai._get_client")
    def test_get_model_settings_returns_toggle_when_thinking_level_is_unsupported(
        self,
        mock_get_client,
        _mock_close_client,
    ):
        client = Mock()
        client.models.get.return_value = {
            "name": "models/gemini-2.5-flash",
            "supported_actions": ["generateContent"],
            "thinking": True,
            "tools": True,
            "output_token_limit": 65536,
        }

        # Simulate the Gemini generation endpoint.
        def generate_content(*, model, contents, config):
            thinking_config = config.get("thinking_config", {})
            if thinking_config.get("thinking_level") is not None:
                raise FakeGoogleError(
                    400,
                    "INVALID_ARGUMENT",
                    "Thinking level is not supported for this model.",
                )
            return {"candidates": [{"content": {"parts": [{"text": "OK"}]}}]}

        client.models.generate_content.side_effect = generate_content
        mock_get_client.return_value = client

        payload = get_google_genai_model_settings("gemini-2.5-flash")

        self.assertTrue(payload["supports_thinking"])
        self.assertTrue(payload["supports_think_toggle"])
        self.assertFalse(payload["supports_think_level"])
        self.assertEqual(payload["think_level_options"], [])
        self.assertTrue(payload["defaults"]["include_thoughts"])
        self.assertEqual(payload["defaults"]["max_output_tokens"], 8192)
        self.assertEqual(payload["runtime_limits"]["output_token_limit"], 65536)
        self.assertNotIn("thinking_level", payload["supported_parameters"])

    # Test generate retries without thinking level when model rejects it.
    @patch("API.google_genai._close_client")
    @patch("API.google_genai._get_client")
    def test_generate_retries_without_thinking_level_when_model_rejects_it(
        self,
        mock_get_client,
        _mock_close_client,
    ):
        client = Mock()
        captured_configs: list[dict[str, object]] = []

        # Simulate a retry flow that rejects thinking_level once.
        def generate_content(*, model, contents, config):
            captured_configs.append(config)
            thinking_config = dict(config.get("thinking_config", {}) or {})
            if thinking_config.get("thinking_level") is not None:
                raise FakeGoogleError(
                    400,
                    "INVALID_ARGUMENT",
                    "Thinking level is not supported for this model.",
                )
            return {"candidates": [{"content": {"parts": [{"text": "Final answer"}]}}]}

        client.models.generate_content.side_effect = generate_content
        mock_get_client.return_value = client

        chunks = list(
            generate_google_genai(
                "gemini-2.5-flash",
                [{"role": "user", "content": "Hi"}],
                stream=False,
                think_level="high",
            )
        )

        self.assertTrue(any(chunk.get("message", {}).get("content") == "Final answer" for chunk in chunks))
        self.assertEqual(len(captured_configs), 2)
        self.assertEqual(
            captured_configs[0]["thinking_config"]["thinking_level"],
            "HIGH",
        )
        self.assertNotIn("thinking_level", captured_configs[1]["thinking_config"])
        cached_capabilities = google_genai_api._get_cached_model_capabilities("gemini-2.5-flash")
        self.assertFalse(cached_capabilities["supports_think_level"])

    # Test learned availability is scoped to API key.
    @patch("API.google_genai._close_client")
    @patch("API.google_genai._get_client")
    @patch("API.google_genai.settings.get_engine_url", return_value="https://generativelanguage.googleapis.com")
    def test_learned_availability_is_scoped_to_api_key(
        self,
        _mock_engine_url,
        mock_get_client,
        _mock_close_client,
    ):
        client_blocked = Mock()
        client_allowed = Mock()
        payloads = [{"name": "models/gemini-3.1-pro", "supported_actions": ["generateContent"]}]
        client_blocked.models.list.side_effect = lambda config=None: payloads
        client_allowed.models.list.side_effect = lambda config=None: payloads
        client_blocked.models.generate_content.side_effect = FakeGoogleError(
            429,
            "RESOURCE_EXHAUSTED",
            "Quota exceeded for model gemini-3.1-pro. limit: 0.",
            details=[{"violations": [{"quotaDimensions": {"model": "gemini-3.1-pro"}}]}],
        )
        client_allowed.models.generate_content.return_value = {
            "candidates": [{"content": {"parts": [{"text": "OK"}]}}]
        }
        key_state = {"value": "key-a"}

        # Get API key.
        def get_api_key():
            return key_state["value"]

        # Get client for key.
        def get_client_for_key():
            return client_blocked if key_state["value"] == "key-a" else client_allowed

        mock_get_client.side_effect = get_client_for_key

        with patch("API.google_genai.settings.get_google_genai_api_key", side_effect=get_api_key):
            with self.assertRaises(FakeGoogleError):
                list(
                    generate_google_genai(
                        "gemini-3.1-pro",
                        [{"role": "user", "content": "Hi"}],
                        stream=False,
                    )
                )
            self.assertEqual(get_google_genai_models(), [])
            key_state["value"] = "key-b"
            models = get_google_genai_models()

        self.assertEqual([entry["model"] for entry in models], ["gemini-3.1-pro"])
        self.assertEqual(client_blocked.models.generate_content.call_count, 1)
        client_allowed.models.generate_content.assert_not_called()


# Cover generic engine registry behavior for optional capabilities.
class EngineRegistryTests(SimpleTestCase):
    """Cover generic engine registry behavior for optional capabilities."""

    # Test reload model raises for engines without reload support.
    def test_reload_model_raises_for_engines_without_reload_support(self):
        with self.assertRaises(NotImplementedError):
            llm_api.reload_model("openai", "gpt-oss")

    # Test get models prepares runtime before listing.
    @patch("API.llm_api.prepare_runtime")
    @patch("API.llm_api._get_engine_module")
    def test_get_models_prepares_runtime_before_listing(self, mock_get_engine_module, mock_prepare_runtime):
        mock_module = Mock()
        mock_module.get_models.return_value = ["llama3"]
        mock_get_engine_module.return_value = mock_module

        self.assertEqual(llm_api.get_models("ollama-service"), ["llama3"])
        mock_prepare_runtime.assert_called_once_with("ollama-service")

    # Test get model settings prepares runtime before loading metadata.
    @patch("API.llm_api.prepare_runtime")
    @patch("API.llm_api._get_engine_module")
    def test_get_model_settings_prepares_runtime_before_loading_metadata(
        self,
        mock_get_engine_module,
        mock_prepare_runtime,
    ):
        mock_module = Mock()
        mock_module.get_model_settings.return_value = {"model": "llama3"}
        mock_get_engine_module.return_value = mock_module

        self.assertEqual(llm_api.get_model_settings("ollama-service", "llama3"), {"model": "llama3"})
        mock_prepare_runtime.assert_called_once_with("ollama-service")


# Cover LM Studio metadata normalization and capability fallback.
class LmsAdapterTests(SimpleTestCase):
    """Cover LM Studio metadata normalization and capability fallback."""

    # Test serialize model info reads nested info wrapper.
    def test_serialize_model_info_reads_nested_info_wrapper(self):
        # Define info.
        class Info:
            model_key = "qwen3"
            display_name = "Qwen 3"
            vision = True
            trained_for_tool_use = True
            max_context_length = 65536

        # Define wrapper.
        class Wrapper:
            info = Info()

        payload = _serialize_model_info(Wrapper())

        self.assertEqual(payload["modelKey"], "qwen3")
        self.assertTrue(payload["vision"])
        self.assertTrue(payload["trainedForToolUse"])
        self.assertEqual(payload["maxContextLength"], 65536)

    # Test get model settings uses loaded model info when direct lookup fails.
    @patch("API.lms._close_client")
    @patch("API.lms._get_client")
    def test_get_model_settings_uses_loaded_model_info_when_direct_lookup_fails(
        self,
        mock_get_client,
        _mock_close_client,
    ):
        # Define loaded info.
        class LoadedInfo:
            model_key = "qwen3"
            vision = True
            trained_for_tool_use = True
            max_context_length = 65536

        # Define loaded model.
        class LoadedModel:
            info = LoadedInfo()

        client = Mock()
        client.llm.get_model_info.side_effect = RuntimeError("not loaded")
        client.list_loaded_models.return_value = [LoadedModel()]
        mock_get_client.return_value = (Mock(), client)

        payload = get_lms_model_settings("qwen3")

        self.assertTrue(payload["supports_vision"])
        self.assertTrue(payload["supports_tool_calling"])
        self.assertEqual(payload["context_length"], 65536)

    # Test prepare OpenAI prediction options keeps LM Studio custom values in extra body.
    def test_prepare_openai_prediction_options_keeps_lms_custom_values_in_extra_body(self):
        payload = _prepare_openai_prediction_options(
            {
                "temperature": 0.2,
                "contextOverflowPolicy": "truncateMiddle",
                "draftModel": "qwen/qwen3.5-0.5b",
            },
            think_level="high",
        )

        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertNotIn("contextOverflowPolicy", payload)
        self.assertEqual(payload["extra_body"]["contextOverflowPolicy"], "truncateMiddle")
        self.assertEqual(payload["extra_body"]["draftModel"], "qwen/qwen3.5-0.5b")
        self.assertIn("reasoningParsing", payload["extra_body"])


# Keep user-visible LM output clean and actionable.
class ViewFormattingTests(SimpleTestCase):
    """Keep user-visible LM output clean and actionable."""

    # Test strip LLM control tokens removes service markers.
    def test_strip_llm_control_tokens_removes_service_markers(self):
        self.assertEqual(
            _strip_llm_control_tokens("<|start|>assistant<|channel|>final<|message|>Hello"),
            "Hello",
        )

    # Test format runtime error hides LM Studio model load verbosity.
    def test_format_runtime_error_hides_lms_model_load_verbosity(self):
        message = _format_runtime_error(
            "lms",
            RuntimeError(
                "Model get/load error: V Cache Quantization requires flash attention to be enabled."
            ),
        )

        self.assertIn("Flash Attention", message)
        self.assertNotIn("Model get/load error", message)


# Exercise chat API basics without calling a real model backend.
class ChatApiTests(ToolRegistryTestMixin, TestCase):
    """Exercise chat API basics without calling a real model backend."""

    # Set up the test fixture.
    def setUp(self):
        super().setUp()
        self.client = Client()

    # Test chat API creates new chat and streams response.
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

    # Test chat API passes selected tool server to Ollama.
    @patch(
        "Apps.UI.views.llm_api.get_model_settings",
        return_value={
            "capabilities": ["tools"],
            "template": "{{ if .Tools }}{{ end }}{{ if .ToolCalls }}{{ end }}",
        },
    )
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_passes_selected_tool_server_to_ollama(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
        _mock_model_settings,
    ):
        self.write_server(
            'time_suite',
            '''
            MCP_SERVER = {"id": "time_suite", "name": "Time Suite"}
            TOOLS = [
                {"id": "time_now", "name": "Current Time", "parameters": {"type": "object", "properties": {}}},
                {"id": "timezone_name", "name": "Timezone Name", "parameters": {"type": "object", "properties": {}}},
            ]
            def call_tool(tool_id, arguments, context=None):
                return "ok"
            ''',
        )
        mock_generate.return_value = [{"message": {"content": "Done"}}]

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"llama3.1","tool_server_id":"time_suite"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'Done')
        self.assertEqual(mock_generate.call_args.kwargs["tool_server_ids"], ["time_suite"])
        self.assertEqual(mock_generate.call_args.kwargs["tool_context"]["engine"], "ollama-service")
        self.assertEqual(Chat.objects.first().active_tool_slug, '["time_suite"]')

    # Test chat API rejects unknown tool server.
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_rejects_unknown_tool_server(self, _mock_engine):
        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"llama3","tool_server_id":"missing"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown or unsupported tool server", response.json()["error"])

    # Test chat API stream includes server and tool markers.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_stream_includes_server_and_tool_markers(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
    ):
        mock_generate.return_value = iter([
            {"message": {"thinking": "Searching..."}},
            {"tool_event": {"server_id": "time_suite", "server_name": "Time Suite", "tool_id": "time_now", "tool_name": "Current Time", "alias": "time_suite__time_now", "arguments": {"label": "now"}}},
            {"message": {"content": "Done"}},
        ])

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"llama3"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        body = b''.join(response.streaming_content).decode('utf-8')
        self.assertIn('<think>\nSearching...', body)
        self.assertIn('\"server_id\": \"time_suite\"', body)
        self.assertIn('\"tool_id\": \"time_now\"', body)
        self.assertIn('Done', body)

    # Test chat API persists generic attachments and builds LM Studio messages.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="lms")
    def test_chat_api_persists_generic_attachments_and_builds_lms_messages(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
    ):
        mock_generate.return_value = [{"message": {"content": "Done"}}]

        response = self.client.post(
            reverse("chat_api"),
            data=json.dumps(
                {
                    "message": "Hello",
                    "model": "qwen",
                    "attachments": [
                        {
                            "kind": "image",
                            "name": "photo.png",
                            "mime_type": "image/png",
                            "data": "iVBORw0KGgo=",
                        },
                        {
                            "kind": "file",
                            "name": "note.txt",
                            "mime_type": "text/plain",
                            "data": "SGVsbG8gZnJvbSBmaWxl",
                        },
                    ],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)
        self.assertEqual(MessageAttachment.objects.count(), 2)

        outbound_messages = mock_generate.call_args.kwargs["messages"]
        current_user_message = outbound_messages[-1]
        self.assertEqual(current_user_message["role"], "user")
        self.assertEqual(len(current_user_message["images"]), 1)
        self.assertIn("[Attached file: note.txt]", current_user_message["content"])
        self.assertIn("Hello from file", current_user_message["content"])

    # Test chat API rejects tool server when LM Studio model lacks tool support.
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings", return_value={"supports_tool_calling": False, "supports_files": True})
    @patch("Apps.UI.views.llm_api.get_model_settings", return_value={"supports_tool_calling": False, "supports_files": True})
    @patch("Apps.UI.views._get_active_engine", return_value="lms")
    def test_chat_api_rejects_tool_server_when_lms_model_lacks_tool_support(
        self,
        _mock_engine,
        _mock_model_settings,
        _mock_preset_model_settings,
    ):
        self.write_server(
            'time_suite',
            '''
            MCP_SERVER = {"id": "time_suite", "name": "Time Suite"}
            TOOLS = [{"id": "time_now", "name": "Current Time", "parameters": {"type": "object", "properties": {}}}]
            def call_tool(tool_id, arguments, context=None):
                return "ok"
            ''',
        )

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"qwen","tool_server_id":"time_suite"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("does not support tool calling", response.json()["error"])

    # Test chat API rejects tool server when Ollama capabilities omit tools.
    @patch(
        "Apps.UI.views.llm_api.get_model_settings",
        return_value={
            "capabilities": ["completion"],
            "template": "{{ if .Tools }}tools{{ end }}{{ if .ToolCalls }}calls{{ end }}",
        },
    )
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_rejects_tool_server_when_ollama_capabilities_omit_tools(
        self,
        _mock_engine,
        _mock_model_settings,
    ):
        self.write_server(
            'time_suite',
            '''
            MCP_SERVER = {"id": "time_suite", "name": "Time Suite"}
            TOOLS = [{"id": "time_now", "name": "Current Time", "parameters": {"type": "object", "properties": {}}}]
            def supports(engine=None, model_name=None):
                return engine == "ollama-service"
            def call_tool(tool_id, arguments, context=None):
                return "ok"
            ''',
        )

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"model-without-tools","tool_server_id":"time_suite"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("does not support tool calling", response.json()["error"])

    # Test chat API rejects tool server when OpenAI model lacks tool support.
    @patch("Apps.UI.views.llm_api.get_model_settings", return_value={"supports_tool_calling": False, "supports_files": True})
    @patch("Apps.UI.views._get_active_engine", return_value="openai")
    def test_chat_api_rejects_tool_server_when_openai_model_lacks_tool_support(
        self,
        _mock_engine,
        _mock_model_settings,
    ):
        self.write_server(
            'time_suite',
            '''
            MCP_SERVER = {"id": "time_suite", "name": "Time Suite"}
            TOOLS = [{"id": "time_now", "name": "Current Time", "parameters": {"type": "object", "properties": {}}}]
            def supports(engine=None, model_name=None):
                return engine == "openai"
            def call_tool(tool_id, arguments, context=None):
                return "ok"
            ''',
        )

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"gpt-test","tool_server_id":"time_suite"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("does not support tool calling", response.json()["error"])


    # Test chat API saves visible content and machine transcript.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_saves_visible_content_and_machine_transcript(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
    ):
        mock_generate.return_value = iter([
            {"message": {"thinking": "Plan first."}},
            {"transcript_message": {"role": "assistant", "content": "", "thinking": "Plan first.", "tool_calls": [{"function": {"name": "time_suite__time_now", "arguments": {"label": "now"}}}]}},
            {"tool_event": {"server_id": "time_suite", "server_name": "Time Suite", "tool_id": "time_now", "tool_name": "Current Time", "alias": "time_suite__time_now", "arguments": {"label": "now"}}},
            {"tool_result": {"role": "tool", "name": "time_suite__time_now", "tool_name": "time_suite__time_now", "content": '{"ok": true}', "server_id": "time_suite", "server_name": "Time Suite", "tool_id": "time_now", "tool_display_name": "Current Time", "arguments": {"label": "now"}}},
            {"message": {"content": "Done"}},
            {"transcript_message": {"role": "assistant", "content": "Done"}},
        ])

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"llama3"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)
        assistant_message = Message.objects.filter(role="assistant").latest("created_at")
        self.assertEqual(assistant_message.content, "Done")
        self.assertEqual(len(assistant_message.llm_transcript), 3)
        self.assertEqual(assistant_message.llm_transcript[1]["role"], "tool")
        self.assertEqual(assistant_message.llm_transcript[1]["server_name"], "Time Suite")

    # Test chat API uses stored transcript for follow up messages.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_uses_stored_transcript_for_follow_up_messages(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
    ):
        chat = Chat.objects.create(title="Chat")
        Message.objects.create(chat=chat, role="user", content="Hello")
        Message.objects.create(
            chat=chat,
            role="assistant",
            content="Visible answer",
            llm_transcript=[
                {"role": "assistant", "content": "", "thinking": "Plan", "tool_calls": [{"function": {"name": "time_suite__time_now", "arguments": {"label": "now"}}}]},
                {"role": "tool", "name": "time_suite__time_now", "tool_name": "time_suite__time_now", "content": '{"ok": true}'},
                {"role": "assistant", "content": "Visible answer"},
            ],
        )
        mock_generate.return_value = [{"message": {"content": "Next"}}]

        response = self.client.post(
            reverse("chat_api"),
            data=f'{{"chat_id":"{chat.id}","message":"Follow up","model":"llama3"}}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)
        history_messages = mock_generate.call_args.kwargs["messages"]
        self.assertEqual([item["role"] for item in history_messages[:4]], ["user", "assistant", "tool", "assistant"])
        self.assertEqual(history_messages[1]["thinking"], "Plan")
        self.assertEqual(history_messages[2]["name"], "time_suite__time_now")
        self.assertEqual(history_messages[-1]["content"], "Follow up")

    # Test chat API strips legacy UI markup when transcript is missing.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_strips_legacy_ui_markup_when_transcript_is_missing(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
    ):
        chat = Chat.objects.create(title="Chat")
        Message.objects.create(chat=chat, role="user", content="Hello")
        Message.objects.create(
            chat=chat,
            role="assistant",
            content='<think>\nPlan\n</think>\n<tool_call>{"alias":"time_suite__time_now"}</tool_call>Visible answer',
        )
        mock_generate.return_value = [{"message": {"content": "Next"}}]

        response = self.client.post(
            reverse("chat_api"),
            data=f'{{"chat_id":"{chat.id}","message":"Follow up","model":"llama3"}}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)
        history_messages = mock_generate.call_args.kwargs["messages"]
        self.assertEqual(history_messages[1], {"role": "assistant", "content": "Visible answer"})

    # Test chat API strips service control tokens from visible output.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="lms")
    def test_chat_api_strips_service_control_tokens_from_visible_output(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
    ):
        mock_generate.return_value = [
            {"message": {"content": "<|start|>assistant<|channel|>final<|message|>Hello"}},
        ]

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hi","model":"qwen3"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content).decode("utf-8"), "Hello")
        assistant_message = Message.objects.filter(role="assistant").latest("created_at")
        self.assertEqual(assistant_message.content, "Hello")


# Verify runtime settings and dynamic model selection endpoints.
class RuntimeSettingsApiTests(TestCase):
    """Verify runtime settings and dynamic model selection endpoints."""

    RUNTIME_SETTINGS_WITH_API_KEY = {
        "llm-engine": "openai",
        "lms_url": "127.0.0.1:1234",
        "openai_url": "openrouter.ai/api/v1",
        "has_openai_api_key": True,
        "engine_urls": {"openai": "https://openrouter.ai/api/v1"},
    }

    # Test get runtime settings payload.
    def test_get_runtime_settings_payload(self):
        response = self.client.get(reverse("runtime_settings_api"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("models", response.json())

    # Test post runtime settings updates engine.
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

    # Test models API returns engine specific models.
    @patch("Apps.UI.views._load_models_for_engine", return_value=["llama3"])
    def test_models_api_returns_engine_specific_models(self, mock_models):
        response = self.client.get(reverse("models_api"), {"engine": "lms"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"engine": "lms", "models": ["llama3"]})
        mock_models.assert_called_once_with("lms")

    # Test runtime settings payload does not expose API key.
    @patch("Apps.UI.views.settings.get_supported_engines", return_value=[])
    @patch("Apps.UI.views.settings.get_runtime_engine_settings", return_value=RUNTIME_SETTINGS_WITH_API_KEY)
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


# Cover local tool-server listing and chat persistence endpoints.
class ToolApiTests(ToolRegistryTestMixin, TestCase):
    """Cover local tool-server listing and chat persistence endpoints."""

    # Test tools API returns discovered servers.
    def test_tools_api_returns_discovered_servers(self):
        self.write_server(
            'time_suite',
            '''
            MCP_SERVER = {"id": "time_suite", "name": "Time Suite", "description": "Time helpers"}
            TOOLS = [{"id": "time_now", "name": "Current Time", "parameters": {"type": "object", "properties": {}}}]
            def call_tool(tool_id, arguments, context=None):
                return "ok"
            ''',
        )

        response = self.client.get(reverse("tools_api"), {"engine": "ollama-service", "model": "llama3"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["tool_servers"],
            [{
                "id": "time_suite",
                "name": "Time Suite",
                "description": "Time helpers",
                "tool_count": 1,
                "tools": [{"id": "time_now", "name": "Current Time", "description": ""}],
            }],
        )

    # Test load chat API returns active tool server id.
    def test_load_chat_api_returns_active_tool_server_id(self):
        chat = Chat.objects.create(title="Chat", active_tool_slug="time_suite")
        Message.objects.create(
            chat=chat,
            role="assistant",
            content="Visible answer",
            llm_transcript=[
                {"role": "assistant", "content": "", "thinking": "Plan"},
                {"role": "tool", "name": "time_suite__time_now", "tool_name": "time_suite__time_now", "content": '{"ok": true}', "server_id": "time_suite", "server_name": "Time Suite", "tool_id": "time_now", "tool_display_name": "Current Time", "arguments": {"label": "now"}},
                {"role": "assistant", "content": "Visible answer"},
            ],
        )

        response = self.client.get(reverse("load_chat_api", args=[chat.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["active_tool_server_id"], "time_suite")
        self.assertEqual(payload["messages"][0]["content"], "Visible answer")
        self.assertEqual(payload["messages"][0]["activity_segments"][0]["type"], "thought")
        self.assertEqual(payload["messages"][0]["activity_segments"][1]["type"], "tool")

    # Test load chat API returns attachment metadata without inline data.
    def test_load_chat_api_returns_attachment_metadata_without_inline_data(self):
        chat = Chat.objects.create(title="Chat")
        message = Message.objects.create(chat=chat, role="user", content="See file")
        attachment = MessageAttachment.objects.create(
            message=message,
            kind="file",
            name="note.txt",
            mime_type="text/plain",
            data="SGVsbG8=",
            size_bytes=5,
        )

        response = self.client.get(reverse("load_chat_api", args=[chat.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        serialized = payload["messages"][0]["attachments"][0]
        self.assertEqual(serialized["id"], attachment.id)
        self.assertEqual(serialized["content_url"], f"/api/attachment/attachment/{attachment.id}/content/")
        self.assertNotIn("data_url", serialized)
        self.assertNotIn("extracted_text", serialized)

    # Test attachment content API streams stored bytes on demand.
    def test_attachment_content_api_streams_stored_bytes(self):
        chat = Chat.objects.create(title="Chat")
        message = Message.objects.create(chat=chat, role="user", content="See file")
        attachment = MessageAttachment.objects.create(
            message=message,
            kind="file",
            name="note.txt",
            mime_type="text/plain",
            data="SGVsbG8=",
            size_bytes=5,
        )

        response = self.client.get(reverse("attachment_content_api", args=["attachment", attachment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"Hello")
        self.assertEqual(response["Content-Type"], "text/plain")


# Cover Ollama preset API endpoints and model-info integration.
class OllamaPresetApiTests(ToolRegistryTestMixin, TestCase):
    """Cover Ollama preset API endpoints and model-info integration."""

    # Test model info includes active Ollama preset defaults and servers.
    @patch("Apps.UI.views.llm_api.get_model_settings")
    def test_model_info_includes_active_ollama_preset_defaults_and_servers(self, mock_get_model_settings):
        self.write_server(
            'time_suite',
            '''
            MCP_SERVER = {"id": "time_suite", "name": "Time Suite", "description": "Time helpers"}
            TOOLS = [
                {"id": "time_now", "name": "Current Time", "parameters": {"type": "object", "properties": {}}},
                {"id": "timezone_name", "name": "Timezone Name", "parameters": {"type": "object", "properties": {}}},
            ]
            def supports(engine=None, model_name=None):
                return engine == "ollama-service"
            def call_tool(tool_id, arguments, context=None):
                return "ok"
            ''',
        )
        OllamaPreset.objects.create(
            model_name="llama3",
            name="Default",
            config={"num_ctx": 32768, "num_predict": 8192},
            is_default=True,
            is_active=False,
        )
        custom_preset = OllamaPreset.objects.create(
            model_name="llama3",
            name="Custom",
            config={"num_ctx": 65536, "mirostat": 2, "numa": True},
            is_default=False,
            is_active=True,
        )
        mock_get_model_settings.return_value = {
            "modelinfo": {"general.architecture.context_length": 131072},
            "parameters": "temperature 0.8\nPARAMETER mirostat 2\nnuma true",
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
        self.assertEqual(payload["available_tool_servers"][0]["id"], "time_suite")
        self.assertEqual(payload["available_tool_servers"][0]["tool_count"], 2)
        self.assertEqual(payload["defaults"]["num_ctx"], 65536)
        self.assertEqual(payload["defaults"]["temperature"], 0.8)
        self.assertEqual(payload["ollama_presets"]["active_preset_id"], str(custom_preset.id))
        self.assertNotIn("mirostat", payload["defaults"])
        self.assertNotIn("numa", payload["defaults"])

    # Test sync endpoint clones default preset on first change.
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

    # Test create rename delete endpoints manage custom preset.
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

    # Test duplicate preset name returns validation error.
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

# Cover LM Studio preset API endpoints and model-info integration.
class LmsPresetApiTests(TestCase):
    """Cover LM Studio preset API endpoints and model-info integration."""

    # Test model info includes active LM Studio preset defaults.
    @patch("Apps.UI.views.llm_api.get_model_settings")
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings")
    def test_model_info_includes_active_lms_preset_defaults(self, mock_preset_settings, mock_model_settings):
        base_settings = {
            "context_length": 65536,
            "defaults": {"temperature": 0.7, "think": True},
            "supports_thinking": True,
            "supports_think_level": False,
            "think_param_name": "think",
            "think_level_param_name": "reasoning_effort",
            "supports_vision": True,
            "supports_tool_calling": True,
            "supports_files": True,
            "runtime_limits": {"gpu_devices": [{"id": 0, "name": "RTX"}], "gpu_count": 1, "main_gpu_max": 0},
            "custom_fields": [],
            "capabilities": ["vision", "tools", "thinking", "files"],
        }
        mock_model_settings.return_value = base_settings
        mock_preset_settings.return_value = base_settings

        default_preset = LmsPreset.objects.create(
            model_name="qwen3",
            name="Default",
            config={"operation": {"temperature": 0.7}},
            is_default=True,
            is_active=False,
        )
        custom_preset = LmsPreset.objects.create(
            model_name="qwen3",
            name="Reasoning Off",
            config={"operation": {"temperature": 0.2, "think": False}},
            is_default=False,
            is_active=True,
        )

        response = self.client.get(
            reverse("model_info_api"),
            {"engine": "lms", "model": "qwen3"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("lms_presets", payload)
        self.assertEqual(payload["defaults"]["temperature"], 0.2)
        self.assertFalse(payload["defaults"]["think"])
        self.assertEqual(payload["lms_presets"]["active_preset_id"], str(custom_preset.id))
        self.assertEqual(default_preset.name, "Default")

    # Test sync endpoint clones default LM Studio preset on first change.
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings")
    def test_sync_endpoint_clones_default_lms_preset_on_first_change(self, mock_get_model_settings):
        mock_get_model_settings.return_value = {
            "defaults": {"temperature": 0.7},
        }

        response = self.client.post(
            reverse("sync_lms_preset_api"),
            data='{"model":"qwen3","config":{"operation":{"temperature":0.2,"think":false}}}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["presets"]), 2)
        self.assertEqual(LmsPreset.objects.filter(model_name="qwen3").count(), 2)
