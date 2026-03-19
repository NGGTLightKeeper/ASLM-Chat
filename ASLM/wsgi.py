# Copyright NGGT.LightKeeper. All Rights Reserved.

import os
from django.core.wsgi import get_wsgi_application


# Configure Django settings module
def _configure_settings_module() -> None:
    """Set the default Django settings module for WSGI startup."""

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ASLM.settings")


# Build WSGI application
def _create_application():
    """Create the Django WSGI application."""

    _configure_settings_module()
    return get_wsgi_application()

application = _create_application()
