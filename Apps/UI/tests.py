"""Tests for ASLM-Chat UI helpers and endpoints."""

from __future__ import annotations

from unittest.mock import patch

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from API.openai import _build_openai_request_options
from Apps.Data.models import Chat
from Apps.UI.views import _extract_model_name


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


class MainViewTests(TestCase):
    """Verify that the main page uses the configured LLM engine helpers."""

    @patch("Apps.UI.views._load_models_for_engine", return_value=["llama3"])
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_main_view_includes_models_and_engine(self, _mock_engine, _mock_models):
        response = self.client.get(reverse("main"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["models"], ["llama3"])
        self.assertEqual(response.context["llm_engine"], "ollama-service")
        self.assertIn("runtime_settings", response.context)


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


class ChatApiTests(TestCase):
    """Exercise chat API basics without calling a real model backend."""

    def setUp(self):
        self.client = Client()

    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_creates_new_chat_and_streams_response(self, _mock_engine, mock_generate):
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


class RuntimeSettingsApiTests(TestCase):
    """Verify runtime settings and dynamic model selection endpoints."""

    @patch("Apps.UI.views._load_models_for_engine", return_value=["gpt-oss"])
    def test_get_runtime_settings_payload(self, mock_models):
        response = self.client.get(reverse("runtime_settings_api"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["models"], ["gpt-oss"])
        mock_models.assert_called_once()

    @patch("Apps.UI.views._load_models_for_engine", return_value=["qwen"])
    def test_post_runtime_settings_updates_engine(self, mock_models):
        response = self.client.post(
            reverse("runtime_settings_api"),
            data='{"llm-engine":"openai","openai_url":"http://127.0.0.1:9000/v1"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["llm-engine"], "openai")
        self.assertEqual(payload["openai_url"], "127.0.0.1:9000/v1")
        self.assertEqual(payload["models"], ["qwen"])
        self.assertFalse(payload["has_openai_api_key"])
        mock_models.assert_called_once_with("openai")

    @patch("Apps.UI.views._load_models_for_engine", return_value=["llama3"])
    def test_models_api_returns_engine_specific_models(self, mock_models):
        response = self.client.get(reverse("models_api"), {"engine": "lms"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"engine": "lms", "models": ["llama3"]})
        mock_models.assert_called_once_with("lms")

    @patch("Apps.UI.views.settings.get_supported_engines", return_value=[])
    @patch("Apps.UI.views._load_models_for_engine", return_value=["gpt-oss"])
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
        _mock_models,
        _mock_engines,
    ):
        response = self.client.get(reverse("runtime_settings_api"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["has_openai_api_key"])
        self.assertNotIn("openai_api_key", payload)
