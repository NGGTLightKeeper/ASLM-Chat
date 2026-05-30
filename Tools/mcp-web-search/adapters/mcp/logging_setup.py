# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Centralized logging setup for mcp-web-search.

Call setup_logging() once at MCP server startup.
Each service emits to its own dedicated log file in logs/.

Log files
---------
logs/web_search.log
logs/read_page.log
logs/web_search_trace.log
logs/read_page_trace.log
logs/mcp_trace.log
logs/core.log
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"

_SERVICE_LOGS: dict[str, str] = {
    "services.web_search": "web_search.log",
    "services.read_page": "read_page.log",
    "trace.web_search": "web_search_trace.log",
    "trace.read_page": "read_page_trace.log",
    "adapters.mcp.server": "mcp_trace.log",
    "mcp_server_bridge": "mcp_trace.log",
    "core": "core.log",
}

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def setup_logging(
    log_dir: Path | None = None,
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> None:
    """Configure rotating file handlers for every service logger."""

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
