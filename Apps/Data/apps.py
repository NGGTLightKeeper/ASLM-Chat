# Copyright NGGT.LightKeeper. All Rights Reserved.

from django.apps import AppConfig


# Configure the data application.
class DataConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "Apps.Data"
