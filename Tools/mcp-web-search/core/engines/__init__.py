# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from .brave import BraveParser
from .duckduckgo import DuckDuckGoParser
from .google import GoogleParser
from .models import EngineParseResult, EngineRequest, ParseStatus, SearchResult

__all__ = [
    "BraveParser",
    "DuckDuckGoParser",
    "EngineParseResult",
    "EngineRequest",
    "GoogleParser",
    "ParseStatus",
    "SearchResult",
]
