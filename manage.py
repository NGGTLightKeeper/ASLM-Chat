# Copyright NGGT.LightKeeper. All Rights Reserved.

import os
import sys


# Configure Django settings module
def _configure_settings_module() -> None:
    """Set the default Django settings module for management commands."""

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ASLM.settings")


# Run Django management entry point
def main() -> None:
    """Run Django administrative tasks."""

    _configure_settings_module()

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
