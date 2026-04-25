# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Shared ThreadPoolExecutor for sync-to-async bridging.

All run_in_executor calls across mcp-web-search use this pool instead of
the default asyncio executor so the pool size is under explicit control and
concurrent web_search + read_page loads cannot exhaust it.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

# Scale with CPU count; floor at 16 so I/O-bound tasks don't queue on
# machines with few cores; cap at 64 to avoid thread-thrashing.
_IO_WORKERS: int = min(64, max(16, (os.cpu_count() or 4) * 4))

io_pool = ThreadPoolExecutor(max_workers=_IO_WORKERS, thread_name_prefix="mcp-io")
