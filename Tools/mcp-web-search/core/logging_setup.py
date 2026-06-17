# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

# Mirrors the legacy adapters/mcp/logging_setup.py: same format, same rotating files,
# same logger names, so logs are byte-compatible with the old pipeline. Covers both the
# web_search and read_page services plus the MCP adapter; serp_api/triage/health/quality
# log under the `core` namespace and land in core.log via propagation.
_LOG_DIR = Path(__file__).resolve().parents[1] / "logs"

_SERVICE_LOGS: dict[str, str] = {
    "services.web_search": "web_search.log",
    "trace.web_search": "web_search_trace.log",
    "services.read_page": "read_page.log",
    "trace.read_page": "read_page_trace.log",
    "mcp.server": "mcp_trace.log",
    # Warm-browser layer (daemon + client + identity store). The daemon runs as its own
    # windowless process, so file logging is the only way to see its activity.
    "core.fetch.browser": "browser_daemon.log",
    "core": "core.log",
}

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


# Configure rotating file handlers for every read_page service logger.
def setup_logging(
    log_dir: Path | None = None,
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> None:
    target_dir = log_dir or _LOG_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    for logger_name, filename in _SERVICE_LOGS.items():
        log = logging.getLogger(logger_name)
        log.setLevel(level)

        if any(isinstance(handler, logging.handlers.RotatingFileHandler) for handler in log.handlers):
            continue

        handler = logging.handlers.RotatingFileHandler(
            target_dir / filename,
            encoding="utf-8",
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        handler.setFormatter(formatter)
        log.addHandler(handler)
        log.propagate = False
