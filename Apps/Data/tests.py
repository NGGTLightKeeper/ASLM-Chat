"""Tests for chat data models."""

from __future__ import annotations

from django.test import TestCase

from Apps.Data.models import Chat, Message, MessageImage, MessageRole


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
