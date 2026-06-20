# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import sys
from collections.abc import Coroutine
from typing import Any


# Run a top-level coroutine on the standard library asyncio loop.
#
# winloop/uvloop were dropped deliberately: their loops reject the `startupinfo`
# argument Playwright passes to create_subprocess_exec ("startupinfo is not
# supported"), which breaks any in-process browser (e.g. cloakbrowser). The stdlib
# Proactor loop on Windows supports subprocess spawning, which Playwright (and thus
# cloakbrowser) relies on.
def run_fast(coro: Coroutine[Any, Any, Any]) -> Any:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    return asyncio.run(coro)
