# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from pathlib import Path


REGISTRY_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = REGISTRY_DIR.parents[1]
CACHE_DIR = PROJECT_ROOT / "_cache"

TRUST_REGISTRY_PATH = REGISTRY_DIR / "trust_registry.json"
DISCOVERED_ENDPOINTS_DB = str(CACHE_DIR / "discovered_endpoints.db")

ENDPOINT_PROBE_RECHECK_TTL_SEC = 86_400
ENDPOINT_PROMOTION_SUCCESS_COUNT = 2
ENDPOINT_DEACTIVATE_FAILURE_COUNT = 3
