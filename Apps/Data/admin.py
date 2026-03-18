"""Admin registrations for ASLM-Chat data models."""

from django.contrib import admin

from Apps.Data.models import Chat, Message, MessageImage, OllamaPreset


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    """Expose persisted chats in the Django admin."""

    list_display = ("title", "active_tool_slug", "created_at", "updated_at")
    search_fields = ("title", "active_tool_slug")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """Expose chat messages in the Django admin."""

    list_display = ("chat", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("content",)


@admin.register(MessageImage)
class MessageImageAdmin(admin.ModelAdmin):
    """Expose stored message images in the Django admin."""

    list_display = ("message", "mime_type", "order")
    list_filter = ("mime_type",)


@admin.register(OllamaPreset)
class OllamaPresetAdmin(admin.ModelAdmin):
    """Expose Ollama presets in the Django admin."""

    list_display = ("model_name", "name", "is_default", "is_active", "updated_at")
    list_filter = ("is_default", "is_active")
    search_fields = ("model_name", "name")
