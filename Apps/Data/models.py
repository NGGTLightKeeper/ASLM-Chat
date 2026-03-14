"""Database models for ASLM-Chat conversation storage."""

from __future__ import annotations

import uuid

from django.db import models


class MessageRole(models.TextChoices):
    """Supported chat roles stored in the local database."""

    USER = "user", "User"
    ASSISTANT = "assistant", "Assistant"
    SYSTEM = "system", "System"


class Chat(models.Model):
    """A single chat thread containing ordered messages."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="New Chat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title


class Message(models.Model):
    """A single message inside a chat thread."""

    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=50, choices=MessageRole.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:50]}"


class MessageImage(models.Model):
    """Store image attachments inline as base64 payloads."""

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="images")
    mime_type = models.CharField(max_length=50, default="image/jpeg")
    data = models.TextField()
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def data_url(self) -> str:
        """Return the stored image payload as a browser-ready data URL."""
        return f"data:{self.mime_type};base64,{self.data}"

    def __str__(self) -> str:
        return f"Image #{self.order} for message {self.message_id}"
