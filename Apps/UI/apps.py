# Copyright NEXTGGTECH. Elastic License 2.0.

import logging
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)


# Configure the UI application.
class UiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "Apps.UI"

    def ready(self) -> None:
        """Prepare enabled engine runtimes without blocking Django startup."""

        def _sync_enabled_engine_runtimes() -> None:
            try:
                from API import llm_api

                llm_api.sync_enabled_engine_runtimes()
            except Exception as exc:
                logger.warning("Failed to sync enabled engine runtimes on startup: %s", exc)

        thread = threading.Thread(
            target=_sync_enabled_engine_runtimes,
            name="aslm-chat-engine-runtime-sync",
            daemon=True,
        )
        thread.start()
