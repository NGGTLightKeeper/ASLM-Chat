# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Fetch over Tor via curl_cffi + socks5h.

curl_cffi (not raw httpx) so the request carries a real browser TLS fingerprint — proven
necessary against fingerprint-gating servers (and harmless for plain onion services). All
requests go through the SOCKS url resolved by tor_proxy; if none is available the fetch is
a no-op returning status="unavailable".
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from core.fetch.thread_pool import io_pool as _io_pool

from .tor_proxy import mark_used, resolve_socks

logger = logging.getLogger("core.fetch.onion.transport")


@dataclass(slots=True)
class OnionFetch:
    url: str
    status: str = "error"          # ok | unavailable | error
    ok: bool = False
    http_status: int = 0
    text: str = ""
    error: str = ""
    ms: float = 0.0


# True when the onion layer can serve a fetch right now (tor enabled + a SOCKS resolved).
def onion_available() -> bool:
    return resolve_socks() is not None


# Blocking curl_cffi GET through the tor SOCKS (runs in the io_pool).
def _get(url: str, socks_url: str, timeout: float, impersonate: str) -> tuple[int, str]:
    from curl_cffi import requests as _r

    resp = _r.get(url, impersonate=impersonate, timeout=max(5.0, timeout),
                  proxies={"http": socks_url, "https": socks_url})
    return resp.status_code, (resp.text or "")


# Fetch one URL over Tor. Never raises — returns an OnionFetch envelope.
async def onion_fetch(url: str, *, timeout: float | None = None,
                      impersonate: str = "chrome124") -> OnionFetch:
    import time

    socks_url = resolve_socks()
    if socks_url is None:
        return OnionFetch(url=url, status="unavailable", error="tor unavailable/disabled")
    mark_used()  # reset the spawned tor's idle timer



    if timeout is None:
        from core.config import load_search_config
        timeout = load_search_config().tor.fetch_timeout

    t0 = time.perf_counter()
    loop = asyncio.get_running_loop()
    try:
        http_status, text = await loop.run_in_executor(
            _io_pool, lambda: _get(url, socks_url, timeout, impersonate)
        )
    except Exception as exc:  # noqa: BLE001
        return OnionFetch(url=url, status="error", error=f"{type(exc).__name__}: {exc}",
                          ms=round((time.perf_counter() - t0) * 1000, 1))
    ok = 200 <= http_status < 300
    return OnionFetch(
        url=url, status="ok" if ok else "error", ok=ok, http_status=http_status,
        text=text, error="" if ok else f"HTTP {http_status}",
        ms=round((time.perf_counter() - t0) * 1000, 1),
    )
