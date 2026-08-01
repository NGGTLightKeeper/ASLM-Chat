# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Process-wide pacing for arXiv's legacy metadata API.

arXiv's published API terms require no more than one legacy-API request every three
seconds and a single connection at a time.  Both academic search and the read_page arXiv
handler share this gate.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

ARXIV_API_ENDPOINT = "https://export.arxiv.org/api/query"
ARXIV_API_MIN_INTERVAL_SECONDS = 3.0

_LOCK = asyncio.Lock()
_last_started = 0.0


@asynccontextmanager
async def arxiv_api_slot() -> AsyncIterator[None]:
    """Serialize legacy API calls and keep their start times at least three seconds apart."""

    global _last_started
    async with _LOCK:
        delay = ARXIV_API_MIN_INTERVAL_SECONDS - (time.monotonic() - _last_started)
        if delay > 0:
            await asyncio.sleep(delay)
        _last_started = time.monotonic()
        yield


__all__ = [
    "ARXIV_API_ENDPOINT",
    "ARXIV_API_MIN_INTERVAL_SECONDS",
    "arxiv_api_slot",
]
