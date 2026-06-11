# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

# Scale with CPU count; floor at 16 so I/O-bound tasks don't queue on few cores;
# cap at 64 to avoid thread thrashing.
_IO_WORKERS: int = min(64, max(16, (os.cpu_count() or 4) * 4))

# Shared pool for sync-to-async bridging (web_search, read_page, etc.).
io_pool = ThreadPoolExecutor(max_workers=_IO_WORKERS, thread_name_prefix="mcp-io")
