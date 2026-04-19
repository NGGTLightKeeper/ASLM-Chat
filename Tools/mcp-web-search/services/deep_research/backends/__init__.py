# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Python backend selection for deep research."""

from __future__ import annotations

from typing import Any

from services.deep_research.backends.python_base import DisabledPythonBackend, PythonBackend
from services.deep_research.backends.python_deep_think import DeepThinkPythonBackend
from services.deep_research.backends.python_mcp_sandbox import MCPSandboxPythonBackend


def build_python_backend(name: str, session: Any = None) -> PythonBackend:
    backend = (name or "deep_think").strip().lower()
    if backend in {"disabled", "none", "off"}:
        return DisabledPythonBackend()
    if backend in {"mcp_sandbox", "mcp-sandbox", "sandbox"}:
        candidate = MCPSandboxPythonBackend(session=session)
        if candidate.available():
            return candidate
        # Sandbox not available — fall back to deep_think so calls aren't wasted on errors.
        return DeepThinkPythonBackend()
    return DeepThinkPythonBackend()
