# Copyright NGGT.LightKeeper. All Rights Reserved.

import os
from django.core.asgi import get_asgi_application


# Configure Django settings module
def _configure_settings_module() -> None:
    """Set the default Django settings module for ASGI startup."""

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ASLM.settings")


# Build ASGI application
def _create_application():
    """Create the Django ASGI application."""

    _configure_settings_module()
    return get_asgi_application()

application = _create_application()
