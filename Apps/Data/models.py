# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import uuid
from django.db import models

class MessageRole(models.TextChoices):
    USER = "user", "User"
    ASSISTANT = "assistant", "Assistant"
    SYSTEM = "system", "System"

class Chat(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="New Chat")
    active_tool_slug = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    # Return chat title
    def __str__(self) -> str:
        """Return the display name for Django admin and logs."""

        return self.title

class Message(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=50, choices=MessageRole.choices)
    content = models.TextField()
    llm_transcript = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    # Return short message preview
    def __str__(self) -> str:
        """Return a compact preview of the stored message."""

        return f"{self.role}: {self.content[:50]}"


class MessageAttachmentKind(models.TextChoices):
    IMAGE = "image", "Image"
    FILE = "file", "File"


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
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def data_url(self) -> str:
        """Return the stored attachment as a data URL."""

        return f"data:{self.mime_type};base64,{self.data}"

    @property
    def is_image(self) -> bool:
        """Return whether the attachment should be treated as an image."""

        return self.kind == MessageAttachmentKind.IMAGE or self.mime_type.startswith("image/")

    def __str__(self) -> str:
        """Return a readable label for the related attachment."""

        label = self.name or f"{self.kind} #{self.order}"
        return f"{label} for message {self.message_id}"


class MessageImage(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="images")
    mime_type = models.CharField(max_length=50, default="image/jpeg")
    data = models.TextField()
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    # Build browser-ready image URL
    def data_url(self) -> str:
        """Return the stored image as a data URL."""

        return f"data:{self.mime_type};base64,{self.data}"

    # Return image label
    def __str__(self) -> str:
        """Return a readable label for the related image."""

        return f"Image #{self.order} for message {self.message_id}"

class OllamaPreset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_name = models.CharField(max_length=255, db_index=True)
    name = models.CharField(max_length=120)
    config = models.JSONField(default=dict)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["model_name", "-is_active", "-is_default", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["model_name", "name"],
                name="unique_ollama_preset_name_per_model",
            ),
        ]

    # Return preset label
    def __str__(self) -> str:
        """Return a readable preset name with its model."""

        return f"{self.model_name} :: {self.name}"


class LmsPreset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_name = models.CharField(max_length=255, db_index=True)
    name = models.CharField(max_length=120)
    config = models.JSONField(default=dict)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["model_name", "-is_active", "-is_default", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["model_name", "name"],
                name="unique_lms_preset_name_per_model",
            ),
        ]

    def __str__(self) -> str:
        """Return a readable preset name with its model."""

        return f"{self.model_name} :: {self.name}"
