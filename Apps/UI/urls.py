# Copyright NGGT.LightKeeper. All Rights Reserved.

from django.urls import path

from . import views

urlpatterns = [
    path("", views.MainView.as_view(), name="main"),
    path("chat/<uuid:chat_id>/", views.ChatView.as_view(), name="chat_view"),
    path("profile/", views.ProfileView.as_view(), name="profile"),

    path("api/chat/", views.chat_api, name="chat_api"),
    path("api/chat/abort/", views.abort_generation_api, name="abort_generation_api"),
    path("api/chat/<uuid:chat_id>/", views.load_chat_api, name="load_chat_api"),
    path("api/chat/<uuid:chat_id>/last/", views.delete_last_assistant_api, name="delete_last_assistant_api"),
    path("api/message/<int:message_id>/delete/", views.delete_message_api, name="delete_message_api"),
    path("api/chat/<uuid:chat_id>/rename/", views.rename_chat_api, name="rename_chat_api"),
    path("api/chat/<uuid:chat_id>/delete/", views.delete_chat_api, name="delete_chat_api"),

    path("api/models/", views.get_models_api, name="models_api"),
    path("api/model_info/", views.get_model_info_api, name="model_info_api"),

    path("api/tools/", views.get_tools_api, name="tools_api"),

    path("api/ollama_presets/", views.get_ollama_presets_api, name="ollama_presets_api"),
    path("api/ollama_presets/sync/", views.sync_ollama_preset_api, name="sync_ollama_preset_api"),
    path("api/ollama_presets/select/", views.select_ollama_preset_api, name="select_ollama_preset_api"),
    path("api/ollama_presets/create/", views.create_ollama_preset_api, name="create_ollama_preset_api"),
    path("api/ollama_presets/rename/", views.rename_ollama_preset_api, name="rename_ollama_preset_api"),
    path("api/ollama_presets/delete/", views.delete_ollama_preset_api, name="delete_ollama_preset_api"),
    
    path("api/reload_model/", views.reload_model_api, name="reload_model_api"),
    path("api/runtime_settings/", views.runtime_settings_api, name="runtime_settings_api"),
]
