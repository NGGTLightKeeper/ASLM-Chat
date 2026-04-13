# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
services.deep_research — Modular deep research pipeline.

Public API:
    run_deep_research(question, depth="medium") -> str
"""

from services.deep_research.orchestrator import run_deep_research

__all__ = ["run_deep_research"]
