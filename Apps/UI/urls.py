# Copyright NGGT.LightKeeper. All Rights Reserved.

from django.urls import path

from . import views


# Register page routes and UI APIs.
urlpatterns = [
    # Page routes.
    path("", views.MainView.as_view(), name="main"),
    path("chat/<uuid:chat_id>/", views.ChatView.as_view(), name="chat_view"),
    path("profile/", views.ProfileView.as_view(), name="profile"),

    # Chat APIs.
    path("api/chat/", views.chat_api, name="chat_api"),
    path("api/uploads/", views.upload_files_api, name="uploads_api"),
    path("api/uploads/<str:file_id>/content/", views.uploaded_file_content_api, name="uploaded_file_content_api"),
    path("api/chat/abort/", views.abort_generation_api, name="abort_generation_api"),
    path("api/chat/<uuid:chat_id>/", views.load_chat_api, name="load_chat_api"),
    path("api/chat/<uuid:chat_id>/last/", views.delete_last_assistant_api, name="delete_last_assistant_api"),
    path("api/chat/<uuid:chat_id>/regenerate/", views.regenerate_chat_api, name="regenerate_chat_api"),
    path("api/attachment/<str:record_type>/<int:attachment_id>/content/", views.attachment_content_api, name="attachment_content_api"),
    path("api/shared-file/download/", views.shared_file_download_api, name="shared_file_download_api"),
    path("api/message/<int:message_id>/delete/", views.delete_message_api, name="delete_message_api"),
    path("api/chat/<uuid:chat_id>/rename/", views.rename_chat_api, name="rename_chat_api"),
    path("api/chat/<uuid:chat_id>/delete/", views.delete_chat_api, name="delete_chat_api"),

    # Model discovery APIs.
    path("api/models/", views.get_models_api, name="models_api"),
    path("api/model_info/", views.get_model_info_api, name="model_info_api"),
    path("api/inference_info/", views.get_inference_info_api, name="inference_info_api"),
    path("api/context_usage/", views.get_context_usage_api, name="context_usage_api"),
    path("api/context_compress/", views.context_compress_api, name="context_compress_api"),

    # Tool discovery APIs.
    path("api/tools/", views.get_tools_api, name="tools_api"),
    path("api/mcp_config/", views.mcp_config_api, name="mcp_config_api"),
    path("api/favicon/", views.favicon_api, name="favicon_api"),
    path("api/browser_portal/frame/", views.browser_portal_frame_api, name="browser_portal_frame_api"),
    path("api/browser_portal/event/", views.browser_portal_event_api, name="browser_portal_event_api"),

    # Ollama preset APIs.
    path("api/ollama_presets/", views.get_ollama_presets_api, name="ollama_presets_api"),
    path("api/ollama_presets/sync/", views.sync_ollama_preset_api, name="sync_ollama_preset_api"),
    path("api/ollama_presets/select/", views.select_ollama_preset_api, name="select_ollama_preset_api"),
    path("api/ollama_presets/create/", views.create_ollama_preset_api, name="create_ollama_preset_api"),
    path("api/ollama_presets/rename/", views.rename_ollama_preset_api, name="rename_ollama_preset_api"),
    path("api/ollama_presets/delete/", views.delete_ollama_preset_api, name="delete_ollama_preset_api"),

    # LM Studio preset APIs.
    path("api/lms_presets/", views.get_lms_presets_api, name="lms_presets_api"),
    path("api/lms_presets/sync/", views.sync_lms_preset_api, name="sync_lms_preset_api"),
    path("api/lms_presets/select/", views.select_lms_preset_api, name="select_lms_preset_api"),
    path("api/lms_presets/create/", views.create_lms_preset_api, name="create_lms_preset_api"),
    path("api/lms_presets/rename/", views.rename_lms_preset_api, name="rename_lms_preset_api"),
    path("api/lms_presets/delete/", views.delete_lms_preset_api, name="delete_lms_preset_api"),

    # Runtime configuration API.
    path("api/runtime_settings/", views.runtime_settings_api, name="runtime_settings_api"),
]
