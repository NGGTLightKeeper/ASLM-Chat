# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
core.llm — LLM client and embedding utilities for deep research.

Public API
----------
call_llm(prompt, model, ...)            -> Optional[str]
call_llm_json(prompt, model, ...)       -> Optional[object]
extract_json(text, schema)              -> Optional[object]
get_session() / close_session()         -> aiohttp session lifecycle
"""

from core.llm.llm_client import (
    call_llm,
    call_llm_json,
    extract_json,
    get_session,
    close_session,
    RuntimeProvider,
)

__all__ = [
    "call_llm",
    "call_llm_json",
    "extract_json",
    "get_session",
    "close_session",
    "RuntimeProvider",
]
