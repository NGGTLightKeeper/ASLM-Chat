# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

from datetime import datetime

# Bumped once per Django process start (server restart / worker spawn).
STATIC_CACHE_VERSION: str = datetime.now().strftime("%Y%m%d%H%M%S")
