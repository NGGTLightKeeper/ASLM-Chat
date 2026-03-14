"""Tests for ASLM-Chat UI helpers and endpoints."""

from __future__ import annotations

from unittest.mock import patch

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from Apps.Data.models import Chat
from Apps.UI.views import _extract_model_name


class ModelNameExtractionTests(SimpleTestCase):
    """Cover adapter-specific model list formats."""

    def test_extracts_name_from_string(self):
        self.assertEqual(_extract_model_name("llama3"), "llama3")

    def test_extracts_name_from_mapping(self):
        self.assertEqual(_extract_model_name({"model": "qwen"}), "qwen")
        self.assertEqual(_extract_model_name({"name": "gpt-oss"}), "gpt-oss")


class MainViewTests(TestCase):
    """Verify that the main page uses the configured LLM engine helpers."""

    @patch("Apps.UI.views._load_models_for_engine", return_value=["llama3"])
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_main_view_includes_models_and_engine(self, _mock_engine, _mock_models):
        response = self.client.get(reverse("main"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["models"], ["llama3"])
        self.assertEqual(response.context["llm_engine"], "ollama-service")


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
