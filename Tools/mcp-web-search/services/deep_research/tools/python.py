# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Agentic deep research Python tool."""

from __future__ import annotations

from services.deep_research.backends import build_python_backend
from services.deep_research.models import ResearchSession
from services.deep_research.tools.base import summarize_text


async def run_agent_python(session: ResearchSession, code: str) -> str:
    backend = build_python_backend(str(session.config.python_backend), session=session)
    result = await backend.run(code or "print('No code provided.')", int(session.config.python_timeout_sec))
    session.python_calls += 1
    output = result.stdout or result.stderr or result.error or ""
    summary = summarize_text(output, int(session.config.tool_observation_max_chars))
    session.console_outputs.append(
        f"Python call {session.python_calls} ok={result.ok} elapsed_ms={result.elapsed_ms}\n{summary}"
    )
    return (
        f"Python ok={result.ok} elapsed_ms={result.elapsed_ms} truncated={result.truncated}\n"
        f"{summary}"
    )
