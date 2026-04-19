# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Python execution backend interface for deep research."""

from __future__ import annotations

from typing import Protocol

from services.deep_research.models import PythonResult


class PythonBackend(Protocol):
    def available(self) -> bool:
        """Return whether this backend can execute code."""

    async def run(self, code: str, timeout_sec: int) -> PythonResult:
        """Execute Python code and return captured output."""


class DisabledPythonBackend:
    def available(self) -> bool:
        return False

    async def run(self, code: str, timeout_sec: int) -> PythonResult:
        return PythonResult(ok=False, error="Python tool is disabled.")
