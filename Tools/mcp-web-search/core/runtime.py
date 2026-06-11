# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import sys
from collections.abc import Coroutine
from typing import Any


# Run a top-level coroutine with winloop/uvloop when available, falling back to asyncio.
def run_fast(coro: Coroutine[Any, Any, Any]) -> Any:
    module_name = "winloop" if sys.platform == "win32" else "uvloop"
    try:
        loop_module = __import__(module_name)
    except ImportError:
        return asyncio.run(coro)
    return loop_module.run(coro)
