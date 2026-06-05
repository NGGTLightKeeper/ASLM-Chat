# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


# Resolve the ASLM host module interop base URL from the environment.
def _base_url() -> str:
    url = (os.environ.get("ASLM_MODULE_INTEROP_BASE_URL") or "").strip()
    if not url:
        raise RuntimeError(
            "ASLM_MODULE_INTEROP_BASE_URL is not set. "
            "The host starts this service automatically; ensure moduleInterop.client is enabled in the module manifest."
        )
    return url.rstrip("/") + "/"


# Fetch installed and running modules from GET /v1/registry.
def get_registry() -> dict[str, Any]:
    req = urllib.request.Request(_base_url() + "v1/registry", method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# Ask ASLM to start the given module ids via POST /v1/modules/start.
def request_start(*, caller_module_id: str, module_ids: list[str]) -> dict[str, Any]:
    body = json.dumps(
        {"callerModuleId": caller_module_id, "moduleIds": list(module_ids)},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        _base_url() + "v1/modules/start",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        payload = ex.read().decode("utf-8", errors="replace")
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            raise RuntimeError(f"HTTP {ex.code}: {payload}") from ex
