# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Adapter for the lightweight deep-think Python sandbox."""

from __future__ import annotations

import sys
from pathlib import Path

from services.deep_research.models import PythonResult


class DeepThinkPythonBackend:
    """Use the existing deep-think sandbox adapter when it is available."""

    def __init__(self) -> None:
        self._adapter = None
        self._error = ""
        self._load()

    def _load(self) -> None:
        try:
            tools_root = Path(__file__).resolve().parents[4]
            deep_think_root = tools_root / "mcp-deep-think"
            if str(deep_think_root) not in sys.path:
                sys.path.insert(0, str(deep_think_root))
            from src.sandbox_adapter import sandbox_adapter  # type: ignore

            self._adapter = sandbox_adapter
        except Exception as exc:
            self._adapter = None
            self._error = f"deep_think python backend unavailable: {type(exc).__name__}: {exc}"

    def available(self) -> bool:
        try:
            return bool(self._adapter and self._adapter.available())
        except Exception:
            return False

    async def run(self, code: str, timeout_sec: int) -> PythonResult:
        if self._adapter is None:
            return PythonResult(ok=False, error=self._error or "deep_think backend unavailable")
        try:
            result = await self._adapter.run(code, timeout_seconds=timeout_sec)
            return PythonResult(
                ok=bool(getattr(result, "ok", False)),
                stdout=str(getattr(result, "stdout", "") or ""),
                stderr=str(getattr(result, "stderr", "") or ""),
                error=getattr(result, "error", None),
                elapsed_ms=int(getattr(result, "elapsed_ms", 0) or 0),
                truncated=bool(getattr(result, "truncated", False)),
            )
        except Exception as exc:
            return PythonResult(ok=False, error=f"deep_think backend error: {type(exc).__name__}: {exc}")
