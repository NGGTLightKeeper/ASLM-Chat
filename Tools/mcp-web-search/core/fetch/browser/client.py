# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Client seam for the warm-browser layer.

Everything in the search pipeline depends only on this module's `browser_fetch`,
`browser_available` and `shutdown_browser` — never on cloakbrowser, the daemon, or
Camoufox directly. The backend (warm daemon vs legacy subprocess) is chosen from
config here, so callers never branch on it.

  warm   → HTTP POST to the persistent cloakbrowser daemon (chromium).
  legacy → one-shot Camoufox subprocess (the disposable-safety fallback path).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from core.config import load_search_config

from .models import (
    STATUS_BLOCKED,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_UNAVAILABLE,
    BrowserFetch,
)

logger = logging.getLogger("core.fetch.browser.client")

# Health probes are cached briefly so per-fetch availability checks stay free.
_HEALTH_TTL = 5.0


# Routes page fetches to the configured browser backend (warm daemon or legacy subprocess).
class BrowserClient:

    def __init__(self, cfg=None) -> None:
        self._cfg = cfg or load_search_config().browser
        self._http: Any | None = None              # lazily-built httpx.AsyncClient
        self._health_ok = False
        self._health_checked_at = 0.0

    # The browser layer is usable when not disabled and the chosen backend is reachable.
    async def available(self) -> bool:
        if self._cfg.browser_fallback == "off":
            return False
        if self._cfg.browser_backend == "legacy":
            from core.fetch.camoufox_fetcher import is_camoufox_available

            return is_camoufox_available()
        return await self._daemon_healthy()

    # Cached daemon /health probe.
    async def _daemon_healthy(self) -> bool:
        now = time.monotonic()
        if now - self._health_checked_at < _HEALTH_TTL:
            return self._health_ok
        self._health_checked_at = now
        try:
            client = self._client()
            resp = await client.get(f"{self._cfg.daemon_url}/health")
            self._health_ok = resp.status_code == 200
        except Exception as exc:  # noqa: BLE001
            logger.debug("browser daemon health probe failed: %s", exc)
            self._health_ok = False
        return self._health_ok

    # Build (once) the shared httpx client for daemon calls.
    def _client(self):
        if self._http is None:
            import httpx

            self._http = httpx.AsyncClient(timeout=self._cfg.fetch_timeout + 5.0)
        return self._http

    # Fetch one URL through the configured backend; never raises — returns a BrowserFetch.
    async def fetch(
        self,
        url: str,
        *,
        wait_sec: float | None = None,
        nav_timeout: float | None = None,
        family: str = "",
    ) -> BrowserFetch:
        if self._cfg.browser_fallback == "off":
            return BrowserFetch(url=url, status=STATUS_UNAVAILABLE, error="browser disabled")
        if self._cfg.browser_backend == "legacy":
            return await self._fetch_legacy(url, wait_sec=wait_sec, nav_timeout=nav_timeout)
        return await self._fetch_warm(url, wait_sec=wait_sec, nav_timeout=nav_timeout, family=family)

    # Warm path: POST /fetch to the daemon and adapt the JSON body to a BrowserFetch.
    async def _fetch_warm(
        self, url: str, *, wait_sec: float | None, nav_timeout: float | None, family: str
    ) -> BrowserFetch:
        payload: dict[str, Any] = {"url": url, "engine": self._cfg.engine}
        if wait_sec is not None:
            payload["wait_ms"] = int(max(0.0, wait_sec) * 1000)
        if nav_timeout is not None:
            payload["timeout_ms"] = int(max(0.1, nav_timeout) * 1000)
        if family:
            payload["family"] = family
        try:
            client = self._client()
            resp = await client.post(f"{self._cfg.daemon_url}/fetch", json=payload)
        except Exception as exc:  # noqa: BLE001
            logger.debug("browser daemon fetch failed for %s: %s", url, exc)
            self._health_ok = False
            return BrowserFetch(url=url, status=STATUS_UNAVAILABLE, backend="warm", error=str(exc))
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            return BrowserFetch(url=url, status=STATUS_ERROR, backend="warm",
                                error=f"bad daemon response (HTTP {resp.status_code})")
        return BrowserFetch.from_daemon(body, backend="warm")

    # Legacy path: one-shot Camoufox subprocess adapted to a BrowserFetch.
    async def _fetch_legacy(
        self, url: str, *, wait_sec: float | None, nav_timeout: float | None
    ) -> BrowserFetch:
        from core.fetch.camoufox_fetcher import fetch_with_camoufox

        timeout = nav_timeout if nav_timeout is not None else self._cfg.nav_timeout
        result = await fetch_with_camoufox(
            url,
            wait_sec=self._cfg.wait if wait_sec is None else wait_sec,
            headless=self._cfg.headless,
            humanize=self._cfg.humanize,
            timeout_sec=float(timeout),
            normalize=False,
        )
        if result.success and result.html:
            status = STATUS_OK
        elif "antibot" in (result.error or "").lower():
            status = STATUS_BLOCKED
        else:
            status = STATUS_ERROR
        return BrowserFetch(
            url=url, status=status, html=result.html, text=result.text, title=result.title,
            engine="camoufox", backend="legacy", ms=result.duration_sec * 1000, error=result.error,
        )

    # Close the shared HTTP client (daemon lifecycle is not owned by the client).
    async def aclose(self) -> None:
        if self._http is not None:
            try:
                await self._http.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._http = None


_client: Optional[BrowserClient] = None


# Lazily-initialised process-wide BrowserClient singleton.
def get_browser_client() -> BrowserClient:
    global _client
    if _client is None:
        _client = BrowserClient()
    return _client


# True when the configured browser backend may be used right now.
async def browser_available() -> bool:
    return await get_browser_client().available()


# Fetch one URL through the configured browser backend (never raises).
async def browser_fetch(
    url: str, *, wait_sec: float | None = None, nav_timeout: float | None = None, family: str = ""
) -> BrowserFetch:
    return await get_browser_client().fetch(
        url, wait_sec=wait_sec, nav_timeout=nav_timeout, family=family
    )


# Release the client's HTTP resources (wire into the MCP server shutdown hook).
async def shutdown_browser() -> None:
    if _client is not None:
        await _client.aclose()
