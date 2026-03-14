"""Route definitions for the ASLM-Chat UI app."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.MainView.as_view(), name="main"),
    path("chat/<uuid:chat_id>/", views.ChatView.as_view(), name="chat_view"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("api/chat/", views.chat_api, name="chat_api"),
    path("api/chat/<uuid:chat_id>/", views.load_chat_api, name="load_chat_api"),
    path("api/model_info/", views.get_model_info_api, name="model_info_api"),
]
