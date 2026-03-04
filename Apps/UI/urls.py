from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.main.as_view(), name='main'),
    path('profile/', views.profile.as_view(), name='profile'),
]
