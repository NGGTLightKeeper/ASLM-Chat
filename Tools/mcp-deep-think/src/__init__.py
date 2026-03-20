# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from .config import settings
from .orchestrator import orchestrator

__all__ = ["mcp", "main", "orchestrator", "settings"]


def __getattr__(name: str):
    """Lazily resolve server exports to avoid package import cycles."""

    if name in {"main", "mcp"}:
        from .server import main, mcp

        return {"main": main, "mcp": mcp}[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
