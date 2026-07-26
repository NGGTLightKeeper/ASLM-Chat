"""First-class Deep Research runtime used directly by the chat application.

Deep Research is intentionally not exposed as an MCP server or a
model-selectable tool. The package owns its control plane, orchestration,
application service, and report exporters in one place.
"""

from . import control, export, service

__all__ = ["control", "export", "service"]
