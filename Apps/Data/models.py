# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import uuid

from django.db import models


# Define available chat message roles.
class MessageRole(models.TextChoices):
    USER = "user", "User"
    ASSISTANT = "assistant", "Assistant"
    SYSTEM = "system", "System"


# Store chat thread metadata.
class Chat(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="New Chat")
    active_tool_slug = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Configure default chat ordering.
    class Meta:
        ordering = ["-updated_at"]

    # Return the chat title.
    def __str__(self) -> str:
        """Return the display name for Django admin and logs."""

        return self.title


# Store persisted chat messages.
class Message(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=50, choices=MessageRole.choices)
    content = models.TextField()
    llm_transcript = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Configure chronological message ordering.
    class Meta:
        ordering = ["created_at"]

    # Return a short message preview.
    def __str__(self) -> str:
        """Return a compact preview of the stored message."""

        return f"{self.role}: {self.content[:50]}"


# Link one copied conversation branch to the exact messages where it diverged.
class ChatBranch(models.Model):
    source_chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="outgoing_branches")
    source_message = models.ForeignKey(
        Message,
        on_delete=models.SET_NULL,
        related_name="outgoing_branches",
        null=True,
        blank=True,
    )
    child_chat = models.OneToOneField(Chat, on_delete=models.CASCADE, related_name="incoming_branch")
    child_message = models.ForeignKey(
        Message,
        on_delete=models.SET_NULL,
        related_name="incoming_branch_markers",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        """Return a readable source-to-child branch label."""

        return f"{self.source_chat} -> {self.child_chat}"


# Define supported attachment kinds.
class MessageAttachmentKind(models.TextChoices):
    IMAGE = "image", "Image"
    FILE = "file", "File"
    URL = "url", "URL"


# Store normalized message attachments.
class MessageAttachment(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="attachments")
    kind = models.CharField(
        max_length=16,
        choices=MessageAttachmentKind.choices,
        default=MessageAttachmentKind.FILE,
    )
    name = models.CharField(max_length=255, blank=True, default="")
    mime_type = models.CharField(max_length=100, default="application/octet-stream")
    data = models.TextField()
    size_bytes = models.PositiveIntegerField(default=0)
    extracted_text = models.TextField(blank=True, default="")
    extracted_text_ready = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    # Configure stable attachment ordering.
    class Meta:
        ordering = ["order", "id"]

    # Build a browser-ready attachment URL.
    def data_url(self) -> str:
        """Return the stored attachment as a data URL."""

        return f"data:{self.mime_type};base64,{self.data}"

    # Return whether the attachment is an image.
    @property
    def is_image(self) -> bool:
        """Return whether the attachment should be treated as an image."""

        return self.kind == MessageAttachmentKind.IMAGE or self.mime_type.startswith("image/")

    # Return a readable attachment label.
    def __str__(self) -> str:
        """Return a readable label for the related attachment."""

        label = self.name or f"{self.kind} #{self.order}"
        return f"{label} for message {self.message_id}"


# Store legacy image-only attachments.
class MessageImage(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="images")
    mime_type = models.CharField(max_length=50, default="image/jpeg")
    data = models.TextField()
    order = models.PositiveSmallIntegerField(default=0)

    # Configure stable legacy image ordering.
    class Meta:
        ordering = ["order"]

    # Build a browser-ready image URL.
    def data_url(self) -> str:
        """Return the stored image as a data URL."""

        return f"data:{self.mime_type};base64,{self.data}"

    # Return a readable image label.
    def __str__(self) -> str:
        """Return a readable label for the related image."""

        return f"Image #{self.order} for message {self.message_id}"


# Store Ollama model presets.
class OllamaPreset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_name = models.CharField(max_length=255, db_index=True)
    name = models.CharField(max_length=120)
    config = models.JSONField(default=dict)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Configure ordering and uniqueness for Ollama presets.
    class Meta:
        ordering = ["model_name", "-is_active", "-is_default", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["model_name", "name"],
                name="unique_ollama_preset_name_per_model",
            ),
        ]

    # Return a readable preset label.
    def __str__(self) -> str:
        """Return a readable preset name with its model."""

        return f"{self.model_name} :: {self.name}"


# Store LM Studio model presets.
class LmsPreset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_name = models.CharField(max_length=255, db_index=True)
    name = models.CharField(max_length=120)
    config = models.JSONField(default=dict)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Configure ordering and uniqueness for LM Studio presets.
    class Meta:
        ordering = ["model_name", "-is_active", "-is_default", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["model_name", "name"],
                name="unique_lms_preset_name_per_model",
            ),
        ]

    # Return a readable preset label.
    def __str__(self) -> str:
        """Return a readable preset name with its model."""

        return f"{self.model_name} :: {self.name}"


# Store OpenAI-compatible model presets, scoped by endpoint to avoid collisions.
class OpenAiPreset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # The endpoint URL is part of the identity so the same model name served by
    # different providers keeps independent presets.
    endpoint_url = models.CharField(max_length=500, blank=True, default="", db_index=True)
    model_name = models.CharField(max_length=255, db_index=True)
    name = models.CharField(max_length=120)
    config = models.JSONField(default=dict)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Configure ordering and uniqueness for OpenAI presets.
    class Meta:
        ordering = ["endpoint_url", "model_name", "-is_active", "-is_default", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint_url", "model_name", "name"],
                name="unique_openai_preset_name_per_endpoint_model",
            ),
        ]

    # Return a readable preset label.
    def __str__(self) -> str:
        """Return a readable preset name with its endpoint and model."""

        return f"{self.endpoint_url} :: {self.model_name} :: {self.name}"


# Store Google GenAI (Gemini) model presets.
class GoogleGenAiPreset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_name = models.CharField(max_length=255, db_index=True)
    name = models.CharField(max_length=120)
    config = models.JSONField(default=dict)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Configure ordering and uniqueness for Google GenAI presets.
    class Meta:
        ordering = ["model_name", "-is_active", "-is_default", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["model_name", "name"],
                name="unique_google_genai_preset_name_per_model",
            ),
        ]

    # Return a readable preset label.
    def __str__(self) -> str:
        """Return a readable preset name with its model."""

        return f"{self.model_name} :: {self.name}"
