from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.main.as_view(), name='Main'),
    path('profile/', views.profile.as_view(), name='Profile'),
    path('api/chat/', views.chat_api, name='chat_api'),
    path('api/chat/<uuid:chat_id>/', views.load_chat_api, name='load_chat_api'),
    path('api/model_info/', views.get_model_info_api, name='model_info_api'),
]
