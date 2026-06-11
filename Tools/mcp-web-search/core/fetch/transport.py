# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import aiohttp
import primp

from ..engines.models import EngineRequest
from ._base import TransportResponse
from .httpx_transport import HttpxTransport

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# One pooled aiohttp session shared by all engine requests.
class AiohttpTransport:

    # Initialize timeout and connection pool settings without opening a session yet.
    def __init__(self, *, timeout_seconds: float = 8.0, connection_limit: int = 12) -> None:
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.connection_limit = max(1, int(connection_limit))
        self._session: aiohttp.ClientSession | None = None

    # Open a new aiohttp session if one is not already active.
    async def start(self) -> None:
        if self._session is not None and not self._session.closed:
            return
        connector = aiohttp.TCPConnector(
            limit=self.connection_limit,
            limit_per_host=4,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
            keepalive_timeout=30.0,
        )
        timeout = aiohttp.ClientTimeout(
            total=self.timeout_seconds,
            connect=min(3.0, self.timeout_seconds),
            sock_connect=min(3.0, self.timeout_seconds),
            sock_read=self.timeout_seconds,
        )
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=DEFAULT_HEADERS,
            auto_decompress=True,
            raise_for_status=False,
        )

    # Close and discard the active aiohttp session.
    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    # Send one HTTP request and return the raw response.
    async def fetch(self, request: EngineRequest) -> TransportResponse:
        await self.start()
        assert self._session is not None
        headers = dict(request.headers)
        if request.cookies:
            headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in request.cookies.items())
        async with self._session.request(
            request.method,
            request.url,
            params=request.params or None,
            data=request.data or None,
            headers=headers or None,
            allow_redirects=True,
        ) as response:
            return TransportResponse(status=response.status, body=await response.read(), transport="aiohttp")


# Bounded browser-impersonating transport for engines that reject generic TLS clients.
class PrimpTransport:

    # Initialize timeout and a thread-pool executor for blocking primp calls.
    def __init__(self, *, timeout_seconds: float = 8.0, max_workers: int = 2) -> None:
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)),
            thread_name_prefix="serp-primp",
        )
        self._clients: dict[str, primp.Client] = {}

    # Return or create a primp client keyed by host+impersonation identity.
    def _client(self, host: str, primp_target: str, primp_os: str) -> primp.Client:
        key = f"{host}:{primp_target}:{primp_os}"
        client = self._clients.get(key)
        if client is None:
            client = primp.Client(
                timeout=self.timeout_seconds,
                impersonate=primp_target,
                impersonate_os=primp_os,
                verify=True,
            )
            self._clients[key] = client
        return client

    # Execute one HTTP request synchronously using the matching primp client.
    def _fetch_sync(self, request: EngineRequest) -> TransportResponse:
        host = request.url.split("/", 3)[2]
        headers = dict(request.headers)
        if request.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in request.cookies.items())
        response = self._client(host, request.primp_target, request.primp_os).request(
            request.method,
            request.url,
            params=request.params or None,
            data=request.data or None,
            headers=headers or None,
        )
        return TransportResponse(status=response.status_code, body=response.content, transport="primp")

    # Run the blocking primp fetch on the thread-pool executor.
    async def fetch(self, request: EngineRequest) -> TransportResponse:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._fetch_sync, request)

    # Release all cached clients and shut down the executor.
    async def close(self) -> None:
        self._clients.clear()
        self._executor.shutdown(wait=False, cancel_futures=True)


# Route each engine to one known transport without retry chains.
class AdaptiveTransport:

    # Initialize all transports: fast aiohttp for DDG, primp for Brave, httpx for Google.
    def __init__(self, *, timeout_seconds: float = 8.0) -> None:
        self._fast = AiohttpTransport(timeout_seconds=timeout_seconds)
        self._impersonated = PrimpTransport(timeout_seconds=timeout_seconds)
        self._httpx = HttpxTransport(timeout_seconds=timeout_seconds)

    # Forward the request to the appropriate transport based on the target host.
    async def fetch(self, request: EngineRequest) -> TransportResponse:
        host = request.url.split("/", 3)[2]
        if host == "www.google.com":
            return await self._httpx.fetch(request)
        if host == "search.brave.com":
            return await self._impersonated.fetch(request)
        return await self._fast.fetch(request)

    # Close all underlying transports.
    async def close(self) -> None:
        await self._fast.close()
        await self._impersonated.close()
        await self._httpx.close()
