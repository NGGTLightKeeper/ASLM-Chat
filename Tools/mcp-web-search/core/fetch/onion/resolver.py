# Copyright NEXTGGTECH. Elastic License 2.0.

"""Resolve the current onion address of a vetted service from its clearnet anchor.

Trust model: the address comes from the service's OWN TLS clearnet site (its
`Onion-Location` header), fetched over clearnet (not Tor) so the https cert anchors trust.
A v3 onion self-authenticates on connect, so a refreshed address can't be MITM'd, and an
operator key rotation is picked up automatically. The seeded `onion` is only a fallback
when the anchor is unreachable. Results are cached with a TTL so we refresh rarely.
"""

from __future__ import annotations

import logging
import threading
import time

from .models import OnionService
from .registry import load_services

logger = logging.getLogger("core.fetch.onion.resolver")

_DEFAULT_TTL = 86_400.0   # 24h — onion addresses are stable; refresh is cheap insurance
_lock = threading.Lock()
_cache: dict[str, tuple[str, float]] = {}   # name -> (onion_url, fetched_at)


# Read a clearnet anchor's Onion-Location header over plain https (TLS-verified, no Tor).
# Returns the advertised onion URL or None.
def _fetch_onion_location(anchor: str, timeout: float) -> str | None:
    from curl_cffi import requests as _r

    try:
        r = _r.get(anchor, impersonate="chrome124", timeout=max(5.0, timeout), allow_redirects=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("onion-location fetch failed for %s: %s", anchor, exc)
        return None
    value = r.headers.get("onion-location") or r.headers.get("Onion-Location")
    return value.strip() if value else None


# Current onion URL for a service: cached if fresh, else refreshed from the clearnet anchor,
# else the seeded fallback. Never raises — always returns a usable URL (seed at worst).
def resolve_onion(service: OnionService, *, ttl: float = _DEFAULT_TTL,
                  timeout: float = 20.0, force: bool = False) -> str:
    now = time.time()
    with _lock:
        hit = _cache.get(service.name)
        if hit and not force and now - hit[1] < ttl:
            return hit[0]

    fresh = _fetch_onion_location(service.clearnet_anchor, timeout)
    addr = fresh or service.onion
    if fresh and fresh != service.onion:
        logger.info("onion address for %s refreshed from anchor (was seed)", service.name)
    with _lock:
        _cache[service.name] = (addr, now)
    return addr


# Refresh every vetted service's address (e.g. a periodic warm). Returns name -> url.
def resolve_all(*, ttl: float = _DEFAULT_TTL, timeout: float = 20.0) -> dict[str, str]:
    return {s.name: resolve_onion(s, ttl=ttl, timeout=timeout) for s in load_services()}


# Drop the resolver cache (tests / forced refresh).
def reset_cache() -> None:
    with _lock:
        _cache.clear()
