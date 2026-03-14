"""URL configuration for ASLM-Chat."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("Apps.UI.urls")),
]
