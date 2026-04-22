"""Realtime file logging for deep research runs."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def deep_research_log_dir() -> Path:
    return _repo_root() / "logs" / "deep_research" / "logs"


def deep_research_log_path(now: datetime | None = None) -> Path:
    stamp = (now or datetime.now()).strftime("%d_%m_%Y")
    return deep_research_log_dir() / f"deep_research_{stamp}.log"


class DeepResearchRunLogger:
    """Per-run logger that appends realtime events to the daily deep research log."""

    def __init__(self, question: str, depth: str) -> None:
        self.run_id = uuid4().hex[:8]
        self.question = " ".join((question or "").split())
        self.depth = str(depth or "standard").strip().lower() or "standard"
        self.path = deep_research_log_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self._logger = logging.getLogger(f"services.deep_research.runtime.{self.run_id}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False

        self._handler = logging.FileHandler(self.path, encoding="utf-8")
        self._handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        self._logger.addHandler(self._handler)

        self.info("run_started depth=%s question=%s", self.depth, self.question)

    def _format(self, message: str) -> str:
        return f"[run_id={self.run_id}] {message}"

    def info(self, message: str, *args: object) -> None:
        self._logger.info(self._format(message), *args)

    def warning(self, message: str, *args: object) -> None:
        self._logger.warning(self._format(message), *args)

    def error(self, message: str, *args: object) -> None:
        self._logger.error(self._format(message), *args)

    def exception(self, message: str, *args: object) -> None:
        self._logger.exception(self._format(message), *args)

    def event(self, name: str, **payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)
        self.info("%s %s", name, body)

    def close(self) -> None:
        self.info("run_finished")
        self._logger.removeHandler(self._handler)
        self._handler.close()
