# Copyright NGGT.LightKeeper. All Rights Reserved.

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("Apps.UI.urls")),
]
