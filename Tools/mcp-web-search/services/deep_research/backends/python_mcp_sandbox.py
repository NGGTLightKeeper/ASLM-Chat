# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""mcp-sandbox Python backend — delegates to the session's EphemeralSandbox."""

from __future__ import annotations

from typing import Any

from services.deep_research.models import PythonResult


class MCPSandboxPythonBackend:
    """Runs Python via the session's ephemeral Docker container."""

    def __init__(self, session: Any = None) -> None:
        self._session = session

    def available(self) -> bool:
        return (
            self._session is not None
            and getattr(self._session, "sandbox", None) is not None
            and getattr(self._session.sandbox, "running", False)
        )

    async def run(self, code: str, timeout_sec: int) -> PythonResult:
        if not self.available():
            return PythonResult(
                ok=False,
                error="Overdrive sandbox is not running. Start the research session first.",
            )
        return await self._session.sandbox.run_python(code, timeout_sec=timeout_sec)
