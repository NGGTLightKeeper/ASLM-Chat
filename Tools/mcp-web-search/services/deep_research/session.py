# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Session helpers for agentic deep research."""

from __future__ import annotations

from services.deep_research.models import ResearchSession


def build_reflection_summary(session: ResearchSession, max_chars: int = 10_000) -> str:
    parts: list[str] = []
    if session.reflection_log:
        parts.append("Reflection log:")
        parts.extend(f"- {item}" for item in session.reflection_log[-12:])
    if session.gaps:
        parts.append("\nKnown gaps:")
        parts.extend(f"- {item}" for item in session.gaps[-12:])
    if session.claims:
        parts.append("\nWorking claims:")
        parts.extend(f"- {item}" for item in session.claims[-12:])
    text = "\n".join(parts).strip()
    return text[:max_chars] if text else "(empty)"
