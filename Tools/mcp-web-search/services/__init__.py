# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from .web_search import WebSearchService, WebSearchOptions, run_web_search
from .read_page import ReadPageService, ReadPageOptions, run_read_page

__all__ = [
    "WebSearchService", "WebSearchOptions", "run_web_search",
    "ReadPageService", "ReadPageOptions", "run_read_page",
    "run_deep_research",
]


def run_deep_research(question: str, depth: str = "medium"):
    """Lazy-import wrapper so heavy deps are not loaded at server startup."""
    from services.deep_research.orchestrator import run_deep_research as _run
    return _run(question, depth)
