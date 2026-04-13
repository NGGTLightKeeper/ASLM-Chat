# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Logging configuration for deep research pipeline.

Writes to both stderr (for MCP subprocess stdout/stderr drain) and
a per-run log file under ``logs/deep_research/<YYYY-MM-DD_HH-MM-SS>.log``.
Each call to start_new_run() opens a fresh file with the current timestamp.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

_LOG_DIR = Path(__file__).resolve().parents[2] / "logs" / "deep_research"
_COT_LOG_DIR = _LOG_DIR / "cot_logs"

_logger_instance: Optional[logging.Logger] = None
_stderr_handler: Optional[logging.StreamHandler] = None


def get_logger(name: str = "deep_research") -> logging.Logger:
    """Return the deep-research logger, adding stderr handler once."""
    global _logger_instance, _stderr_handler

    logger = logging.getLogger(name)

    if _logger_instance is not None:
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-5s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _stderr_handler = logging.StreamHandler()
    _stderr_handler.setLevel(logging.INFO)
    _stderr_handler.setFormatter(fmt)
    logger.addHandler(_stderr_handler)

    _logger_instance = logger
    return logger


def start_new_run(
    logger: logging.Logger,
    *,
    question: str,
    depth: str,
) -> None:
    """Open a new per-run log file in logs/deep_research/ with a datetime name.

    Old file handlers are closed and removed so each run writes only to its
    own file.  The naming pattern is ``YYYY-MM-DD_HH-MM-SS.log``.
    """
    # Remove any existing file handlers from a previous run.
    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler) and not isinstance(
            handler, logging.StreamHandler
        ):
            try:
                handler.close()
            except Exception:
                pass
            logger.removeHandler(handler)

    # Actually we need to be more precise: StreamHandler IS a base of FileHandler,
    # so let's just target handlers that have a baseFilename attribute.
    for handler in list(logger.handlers):
        if hasattr(handler, "baseFilename"):
            try:
                handler.close()
            except Exception:
                pass
            logger.removeHandler(handler)

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-5s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = _LOG_DIR / f"{timestamp}.log"

    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except Exception as exc:
        logger.warning("Could not create file handler for %s: %s", log_file, exc)
        return

    separator = "=" * 88
    logger.info(separator)
    logger.info(
        "NEW RUN depth=%s file=%s question=%r",
        depth,
        log_file.name,
        question[:240],
    )
    logger.info(separator)


def open_cot_log(question: str) -> Optional[Callable[[str, int], None]]:
    """Open a per-run CoT log in logs/deep_research/cot_logs/<timestamp>.md.

    Returns a sink callable ``(thinking: str, iteration: int) -> None`` that
    appends each reflection's raw reasoning to the file.  Returns None if the
    file cannot be created (non-fatal).
    """
    try:
        _COT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = _COT_LOG_DIR / f"{timestamp}.md"
        log_path.write_text(
            f"# CoT Log\n\n**Question:** {question}\n\n---\n",
            encoding="utf-8",
        )

        def sink(thinking: str, iteration: int) -> None:
            try:
                with open(log_path, "a", encoding="utf-8") as fh:
                    fh.write(
                        f"\n## Iteration {iteration} — reflection\n\n"
                        f"{thinking.strip()}\n\n---\n"
                    )
            except Exception:
                pass

        return sink
    except Exception:
        return None
