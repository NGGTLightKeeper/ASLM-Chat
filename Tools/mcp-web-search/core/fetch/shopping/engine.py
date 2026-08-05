# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import asyncio
from dataclasses import asdict
import time
from typing import Any

import httpx

from .assets import ShoppingAssetCache
from .models import ShoppingProduct, ShoppingProviderAttempt, ShoppingSearchResult
from .parse import parse_products, source_domain
from .providers import ShoppingProvider, providers_for_lane


EFFORT_RATIOS = {
    "low": (0.75, 0.25),
    "medium": (0.60, 0.40),
    "high": (0.50, 0.50),
}
EFFORT_HARD_TIMEOUT_MS = {
    "low": 2500,
    "medium": 5000,
    "high": 9000,
}
REGIONAL_EFFORT_HARD_TIMEOUT_MS = {
    "low": 4000,
    "medium": 7500,
    "high": 10000,
}
EFFORT_BUFFER_GRACE_MS = {
    "low": 0,
    "medium": 350,
    "high": 900,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
}


class ProviderState:
    def __init__(self) -> None:
        self.failures: dict[str, int] = {}
        self.cooldown_until: dict[str, float] = {}
        self.last_status: dict[str, str] = {}

    def available(self, provider: ShoppingProvider) -> bool:
        return self.cooldown_until.get(provider.name, 0.0) <= time.time()

    def record(self, provider: ShoppingProvider, attempt: ShoppingProviderAttempt, product_count: int) -> None:
        bad_status = attempt.status_code in {202, 403, 429, 503}
        failed = (not attempt.ok) or bad_status or product_count <= 0
        self.last_status[provider.name] = str(attempt.status_code or attempt.error or "ok")
        if failed:
            count = self.failures.get(provider.name, 0) + 1
            self.failures[provider.name] = count
            if count >= provider.failure_threshold:
                self.cooldown_until[provider.name] = time.time() + provider.cooldown_sec
                attempt.cooldown_sec = provider.cooldown_sec
            return
        self.failures[provider.name] = 0
        self.cooldown_until.pop(provider.name, None)

    def snapshot(self) -> dict[str, Any]:
        now = time.time()
        return {
            "failures": dict(self.failures),
            "cooldowns": {
                name: max(0, round(until - now, 1))
                for name, until in self.cooldown_until.items()
                if until > now
            },
            "last_status": dict(self.last_status),
        }


# Process-wide provider state so a 403/429 cooldown survives across shopping calls — a new
# engine per call previously reset it, letting a dead provider keep wasting attempts.
_GLOBAL_PROVIDER_STATE = ProviderState()


class ShoppingSearchEngine:
    def __init__(
        self,
        *,
        asset_cache: ShoppingAssetCache | None = None,
        state: ProviderState | None = None,
    ) -> None:
        self.assets = asset_cache or ShoppingAssetCache()
        # Default to the process-wide state so cooldowns persist across calls; tests inject
        # a fresh ProviderState for isolation.
        self.state = state if state is not None else _GLOBAL_PROVIDER_STATE

    async def search(
        self,
        query: str,
        *,
        effort: str = "medium",
        limit: int = 12,
        language: str = "en",
        hard_timeout_ms: int | None = None,
    ) -> ShoppingSearchResult:
        started = time.perf_counter()
        effort = effort if effort in EFFORT_RATIOS else "medium"
        primary_ratio, secondary_ratio = EFFORT_RATIOS[effort]
        primary_limit = max(1, round(limit * primary_ratio))
        secondary_limit = max(0, limit - primary_limit)

        timeout_ms = hard_timeout_ms if hard_timeout_ms is not None else self._hard_timeout_for_effort(effort, language)
        grace_ms = EFFORT_BUFFER_GRACE_MS[effort]
        buffer = _SearchBuffer()
        tasks = {
            asyncio.create_task(self._timed_lane(query, "primary", limit, language=language)): "primary",
            asyncio.create_task(self._timed_secondary_lane(query, limit, language=language)): "secondary",
        }
        partial = False
        partial_reason = ""
        try:
            pending = set(tasks.keys())
            deadline = started + (timeout_ms / 1000)
            while pending:
                timeout = max(0.0, deadline - time.perf_counter())
                if timeout <= 0:
                    break
                done, pending = await asyncio.wait(pending, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    break
                for task in done:
                    lane = tasks[task]
                    try:
                        products, attempts, elapsed_ms = task.result()
                    except Exception as exc:
                        products, attempts, elapsed_ms = [], [], int((time.perf_counter() - started) * 1000)
                        partial = True
                        partial_reason = f"{lane}_error:{type(exc).__name__}"
                    buffer.update(lane, products, attempts, elapsed_ms)
                if pending and self._buffer_can_fill_limit(buffer, primary_limit, secondary_limit, limit):
                    if self._should_wait_for_regional_primary(language, pending, tasks, buffer):
                        continue
                    grace_timeout = min(grace_ms / 1000, max(0.0, deadline - time.perf_counter()))
                    if grace_timeout > 0:
                        grace_done, pending = await asyncio.wait(
                            pending,
                            timeout=grace_timeout,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for task in grace_done:
                            lane = tasks[task]
                            try:
                                products, attempts, elapsed_ms = task.result()
                            except Exception as exc:
                                products, attempts, elapsed_ms = [], [], int((time.perf_counter() - started) * 1000)
                                partial = True
                                partial_reason = f"{lane}_error:{type(exc).__name__}"
                            buffer.update(lane, products, attempts, elapsed_ms)
                    if pending:
                        partial = True
                        partial_reason = partial_reason or "buffer_full"
                        break
            if pending:
                partial = True
                partial_reason = partial_reason or "hard_timeout"
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks.keys(), return_exceptions=True)
            raise

        primary_products = buffer.products.get("primary", [])
        secondary_products = buffer.products.get("secondary", [])
        primary_shortfall = max(0, primary_limit - len(primary_products))
        secondary_fetch_limit = secondary_limit + primary_shortfall
        products, merge_elapsed_ms = self._timed_merge(
            primary_products,
            secondary_products,
            primary_limit,
            secondary_fetch_limit,
            limit,
        )
        favicon_elapsed_ms = self._timed_attach_favicons(products)
        total_elapsed_ms = int((time.perf_counter() - started) * 1000)
        attempts = [*buffer.attempts.get("primary", []), *buffer.attempts.get("secondary", [])]
        if partial and products:
            for product in products:
                product.meta["partial"] = True
                product.meta["partial_reason"] = partial_reason
        return ShoppingSearchResult(
            query=query,
            effort=effort,
            primary_ratio=primary_ratio,
            secondary_ratio=secondary_ratio,
            products=products,
            attempts=attempts,
            provider_state=self.state.snapshot(),
            timings={
                "total_elapsed_ms": total_elapsed_ms,
                "hard_timeout_ms": timeout_ms,
                "buffer_grace_ms": grace_ms,
                "primary_lane_elapsed_ms": buffer.elapsed_ms.get("primary", 0),
                "secondary_lane_elapsed_ms": buffer.elapsed_ms.get("secondary", 0),
                "primary_shortfall": primary_shortfall,
                "secondary_fetch_limit": secondary_fetch_limit,
                "merge_elapsed_ms": merge_elapsed_ms,
                "favicon_elapsed_ms": favicon_elapsed_ms,
                "fetch_elapsed_ms": sum(attempt.elapsed_ms for attempt in attempts),
                "parse_elapsed_ms": sum(attempt.parse_elapsed_ms for attempt in attempts),
            },
            partial=partial,
            partial_reason=partial_reason,
        )

    def _hard_timeout_for_effort(self, effort: str, language: str) -> int:
        lang = (language or "en").split("-", 1)[0].lower()
        if lang != "en":
            return REGIONAL_EFFORT_HARD_TIMEOUT_MS.get(effort, REGIONAL_EFFORT_HARD_TIMEOUT_MS["medium"])
        return EFFORT_HARD_TIMEOUT_MS.get(effort, EFFORT_HARD_TIMEOUT_MS["medium"])

    async def _timed_lane(
        self,
        query: str,
        lane: str,
        limit: int,
        *,
        language: str = "en",
    ) -> tuple[list[ShoppingProduct], list[ShoppingProviderAttempt], int]:
        started = time.perf_counter()
        products, attempts = await self._lane(query, lane, limit, language=language)
        return products, attempts, int((time.perf_counter() - started) * 1000)

    async def _timed_secondary_lane(
        self,
        query: str,
        limit: int,
        *,
        language: str = "en",
    ) -> tuple[list[ShoppingProduct], list[ShoppingProviderAttempt], int]:
        started = time.perf_counter()
        products, attempts = await self._secondary_lane(query, limit, language=language)
        return products, attempts, int((time.perf_counter() - started) * 1000)

    def _buffer_can_fill_limit(
        self,
        buffer: "_SearchBuffer",
        primary_limit: int,
        secondary_limit: int,
        total_limit: int,
    ) -> bool:
        primary_products = buffer.products.get("primary", [])
        secondary_products = buffer.products.get("secondary", [])
        primary_shortfall = max(0, primary_limit - len(primary_products))
        secondary_fetch_limit = secondary_limit + primary_shortfall
        merged = self._merge_products(primary_products, secondary_products, primary_limit, secondary_fetch_limit, total_limit)
        return len(merged) >= total_limit

    def _should_wait_for_regional_primary(
        self,
        language: str,
        pending: set[asyncio.Task],
        tasks: dict[asyncio.Task, str],
        buffer: "_SearchBuffer",
    ) -> bool:
        if (language or "en").split("-", 1)[0].lower() == "en":
            return False
        if buffer.products.get("primary"):
            return False
        return any(tasks.get(task) == "primary" for task in pending)

    async def _lane(
        self,
        query: str,
        lane: str,
        limit: int,
        *,
        language: str = "en",
    ) -> tuple[list[ShoppingProduct], list[ShoppingProviderAttempt]]:
        if limit <= 0:
            return [], []
        attempts: list[ShoppingProviderAttempt] = []
        products: list[ShoppingProduct] = []
        providers = self._ranked_available(lane, language=language)
        for provider in providers:
            provider_products, provider_attempts = await self._provider(query, provider)
            attempts.extend(provider_attempts)
            if provider_products:
                products.extend(provider_products)
                if len(products) >= limit:
                    break
        return products[:limit], attempts

    async def _secondary_lane(
        self,
        query: str,
        limit: int,
        *,
        language: str = "en",
    ) -> tuple[list[ShoppingProduct], list[ShoppingProviderAttempt]]:
        if limit <= 0:
            return [], []
        providers = self._ranked_available("secondary", language=language)
        if not providers:
            return [], []
        main = providers[0]
        backups = providers[1:]
        attempts: list[ShoppingProviderAttempt] = []
        products: list[ShoppingProduct] = []

        first_wave = [asyncio.create_task(self._provider(query, main))]
        if backups:
            first_wave.append(asyncio.create_task(self._provider(query, backups[0])))
        results = await asyncio.gather(*first_wave, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                continue
            provider_products, provider_attempts = result
            attempts.extend(provider_attempts)
            products.extend(provider_products)

        if len(products) < limit and backups:
            attempted = {attempt.provider for attempt in attempts}
            for provider in backups[1:]:
                if provider.name in attempted:
                    continue
                provider_products, provider_attempts = await self._provider(query, provider)
                attempts.extend(provider_attempts)
                products.extend(provider_products)
                if len(products) >= limit:
                    break
        return self._dedupe_products(products)[:limit], attempts

    def _ranked_available(self, lane: str, *, language: str = "en") -> list[ShoppingProvider]:
        providers = providers_for_lane(lane, language=language)
        available = [provider for provider in providers if self.state.available(provider)]
        unavailable = [provider for provider in providers if provider not in available]
        return available + unavailable

    async def _provider(self, query: str, provider: ShoppingProvider) -> tuple[list[ShoppingProduct], list[ShoppingProviderAttempt]]:
        url = provider.url_builder(query)
        attempts: list[ShoppingProviderAttempt] = []
        if not self.state.available(provider):
            attempt = ShoppingProviderAttempt(
                provider=provider.name,
                lane=provider.lane,
                method="cooldown",
                url=url,
                ok=False,
                elapsed_ms=0,
                error="provider in cooldown",
                cooldown_sec=max(0.0, self.state.cooldown_until.get(provider.name, 0.0) - time.time()),
            )
            return [], [attempt]

        for method in provider.methods:
            html, attempt = await self._fetch(url, provider, method)
            attempts.append(attempt)
            parse_started = time.perf_counter()
            products = parse_products(
                html,
                provider=provider.name,
                lane=provider.lane,
                method=method,
                base_url=url,
                default_currency=provider.default_currency,
            )
            attempt.parse_elapsed_ms = int((time.perf_counter() - parse_started) * 1000)
            attempt.products = len(products)
            self.state.record(provider, attempt, len(products))
            if products:
                return products, attempts
            if attempt.status_code in {403, 429, 503}:
                break
        return [], attempts

    async def _fetch(self, url: str, provider: ShoppingProvider, method: str) -> tuple[str, ShoppingProviderAttempt]:
        started = time.perf_counter()
        try:
            if method == "curl_cffi":
                status, text = await asyncio.to_thread(self._fetch_curl_cffi, url, provider.timeout_sec)
            elif method == "httpx":
                status, text = await self._fetch_httpx(url, provider.timeout_sec)
            else:
                raise ValueError(f"unknown method: {method}")
            ok = 200 <= int(status or 0) < 300 and bool(text)
            attempt = ShoppingProviderAttempt(
                provider=provider.name,
                lane=provider.lane,
                method=method,
                url=url,
                ok=ok,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                status_code=int(status or 0),
                bytes=len(text.encode("utf-8", errors="ignore")) if text else 0,
            )
            return text if ok else "", attempt
        except Exception as exc:
            return "", ShoppingProviderAttempt(
                provider=provider.name,
                lane=provider.lane,
                method=method,
                url=url,
                ok=False,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                error=f"{type(exc).__name__}: {exc}",
            )

    async def _fetch_httpx(self, url: str, timeout_sec: float) -> tuple[int, str]:
        async with httpx.AsyncClient(
            headers=HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(timeout_sec, connect=min(2.5, timeout_sec)),
        ) as client:
            response = await client.get(url)
        return response.status_code, response.text

    def _fetch_curl_cffi(self, url: str, timeout_sec: float) -> tuple[int, str]:
        from curl_cffi import requests as cffi_req

        response = cffi_req.get(
            url,
            headers=HEADERS,
            timeout=timeout_sec,
            impersonate="chrome124",
            allow_redirects=True,
        )
        return int(response.status_code), response.text

    def _merge_products(
        self,
        primary: list[ShoppingProduct],
        secondary: list[ShoppingProduct],
        primary_limit: int,
        secondary_limit: int,
        total_limit: int,
    ) -> list[ShoppingProduct]:
        picked = [*primary[:primary_limit], *secondary[:secondary_limit]]
        if len(picked) < total_limit:
            extras = [*primary[primary_limit:], *secondary[secondary_limit:]]
            picked.extend(extras[: total_limit - len(picked)])
        seen: set[str] = set()
        out: list[ShoppingProduct] = []
        for product in picked:
            key = product.url or product.id
            if key in seen:
                continue
            seen.add(key)
            out.append(product)
            if len(out) >= total_limit:
                break
        return out

    def _timed_merge(
        self,
        primary: list[ShoppingProduct],
        secondary: list[ShoppingProduct],
        primary_limit: int,
        secondary_limit: int,
        total_limit: int,
    ) -> tuple[list[ShoppingProduct], int]:
        started = time.perf_counter()
        products = self._merge_products(primary, secondary, primary_limit, secondary_limit, total_limit)
        return products, int((time.perf_counter() - started) * 1000)

    def _timed_attach_favicons(self, products: list[ShoppingProduct]) -> int:
        started = time.perf_counter()
        self._attach_favicons(products)
        return int((time.perf_counter() - started) * 1000)

    def _dedupe_products(self, products: list[ShoppingProduct]) -> list[ShoppingProduct]:
        seen: set[str] = set()
        out: list[ShoppingProduct] = []
        for product in products:
            key = product.url or product.id
            if key in seen:
                continue
            seen.add(key)
            out.append(product)
        return out

    def _attach_favicons(self, products: list[ShoppingProduct]) -> None:
        for product in products:
            domain = product.source_domain or source_domain(product.url)
            product.favicon_url = self.assets.favicon_proxy_url(domain)


async def search_shopping(
    query: str,
    *,
    effort: str = "medium",
    limit: int = 12,
    language: str = "en",
) -> ShoppingSearchResult:
    engine = ShoppingSearchEngine()
    result = await engine.search(query, effort=effort, limit=limit, language=language)
    currency_started = time.perf_counter()
    try:
        from .currency import enrich_products_with_exchange_rates

        result.exchange_rates = await enrich_products_with_exchange_rates(result.products)
    except Exception as exc:  # noqa: BLE001 - keep original shopping prices on FX failure
        result.exchange_rates = {"providers": [], "converted_products": 0, "error": str(exc)}
    result.timings["currency_elapsed_ms"] = int((time.perf_counter() - currency_started) * 1000)
    result.timings["total_elapsed_ms"] = int(result.timings.get("total_elapsed_ms", 0)) + int(
        result.timings["currency_elapsed_ms"]
    )
    return result


def result_to_jsonable(result: ShoppingSearchResult) -> dict[str, Any]:
    return {
        "query": result.query,
        "effort": result.effort,
        "mix": {
            "primary": result.primary_ratio,
            "secondary": result.secondary_ratio,
        },
        "products": [asdict(product) for product in result.products],
        "attempts": [asdict(attempt) for attempt in result.attempts],
        "provider_state": result.provider_state,
        "timings": dict(result.timings),
        "exchange_rates": dict(result.exchange_rates),
        "partial": result.partial,
        "partial_reason": result.partial_reason,
    }


class _SearchBuffer:
    def __init__(self) -> None:
        self.products: dict[str, list[ShoppingProduct]] = {"primary": [], "secondary": []}
        self.attempts: dict[str, list[ShoppingProviderAttempt]] = {"primary": [], "secondary": []}
        self.elapsed_ms: dict[str, int] = {"primary": 0, "secondary": 0}

    def update(
        self,
        lane: str,
        products: list[ShoppingProduct],
        attempts: list[ShoppingProviderAttempt],
        elapsed_ms: int,
    ) -> None:
        self.products[lane] = products
        self.attempts[lane] = attempts
        self.elapsed_ms[lane] = elapsed_ms
