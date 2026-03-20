# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlparse

from .camoufox_engine import CamoufoxEngine
from .dispatcher import MemoryAdaptiveDispatcher
from .nodriver_engine import NodriverEngine
from .proxy_rotator import ProxyRotator

try:
    from ..config import (
        CAMOUFOX_PROFILE_LOCALES,
        CAMOUFOX_PROFILE_OS_WEIGHTS,
        CAMOUFOX_WARMUP_COUNT,
        CAMOUFOX_WARMUP_URLS,
        STEALTH_ENABLE_CAMOUFOX,
        STEALTH_ENABLE_NODRIVER,
    )
except (ImportError, ValueError):
    CAMOUFOX_WARMUP_URLS = []
    CAMOUFOX_WARMUP_COUNT = 0
    CAMOUFOX_PROFILE_LOCALES = ["en-US"]
    CAMOUFOX_PROFILE_OS_WEIGHTS = {"windows": 0.7, "macos": 0.2, "linux": 0.1}
    STEALTH_ENABLE_NODRIVER = False
    STEALTH_ENABLE_CAMOUFOX = True

try:
    from ..domain_registry import get_registry
except (ImportError, ValueError):
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from domain_registry import get_registry

logger = logging.getLogger("stealth.pool")


# Stealth extraction result model.
@dataclass
class StealthResult:
    url: str
    html: Optional[str] = None
    text: Optional[str] = None
    method: str = ""
    success: bool = False
    latency_ms: float = 0.0
    error: Optional[str] = None


# URL helpers.
def _extract_domain(url: str) -> str:
    """Return the normalized host for a URL."""

    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


# Domain capability helpers.
def _is_hardened(url: str) -> bool:
    """Return whether the domain is marked as hardened."""

    reg = get_registry()
    info = reg.lookup(url)
    return info.tier in {"hardened", "fortress"} or info.method in {
        "camoufox",
        "nodriver",
        "skip",
    }


# Domain capability helpers.
def _is_lightweight(url: str) -> bool:
    """Return whether the domain should stay on lightweight fetchers."""

    reg = get_registry()
    info = reg.lookup(url)
    return info.tier == "friendly" and info.method in {
        "http",
        "xml_feed",
        "json_api",
        "official_api",
    }


# Stealth browser pool.
class BrowserPool:
    # Configure engines, proxies, and dispatching.
    def __init__(
        self,
        proxies: Optional[List[str]] = None,
        max_concurrency: int = 6,
        memory_threshold_percent: float = 85.0,
        nodriver_timeout: float = 30.0,
        camoufox_timeout: float = 45.0,
        prefer_camoufox: bool = False,
        enable_nodriver: bool = STEALTH_ENABLE_NODRIVER,
        enable_camoufox: bool = STEALTH_ENABLE_CAMOUFOX,
    ):
        self._proxy_rotator = ProxyRotator(proxies) if proxies else None

        self._nodriver = NodriverEngine(timeout_sec=nodriver_timeout)
        self._camoufox = CamoufoxEngine(
            timeout_sec=camoufox_timeout,
            warmup_urls=CAMOUFOX_WARMUP_URLS,
            warmup_count=CAMOUFOX_WARMUP_COUNT,
            profile_locales=CAMOUFOX_PROFILE_LOCALES,
            profile_os_weights=CAMOUFOX_PROFILE_OS_WEIGHTS,
        )

        self._dispatcher = MemoryAdaptiveDispatcher(
            max_concurrency=max_concurrency,
            memory_threshold_percent=memory_threshold_percent,
        )

        self._prefer_camoufox = prefer_camoufox
        self._enable_nodriver = bool(enable_nodriver)
        self._enable_camoufox = bool(enable_camoufox)
        self._stats = {
            "nodriver_success": 0,
            "nodriver_fail": 0,
            "camoufox_success": 0,
            "camoufox_fail": 0,
            "skipped_lightweight": 0,
        }

    # Check whether Nodriver can be used.
    def _nodriver_ready(self) -> bool:
        """Return whether the Nodriver engine is enabled and available."""

        return self._enable_nodriver and self._nodriver.is_available()

    # Check whether Camoufox can be used.
    def _camoufox_ready(self) -> bool:
        """Return whether the Camoufox engine is enabled and available."""

        return self._enable_camoufox and self._camoufox.is_available()

    # Select the secondary engine.
    def _fallback_engine(self, primary: str) -> str:
        """Return the fallback engine for the current primary choice."""

        if primary == "nodriver":
            return "camoufox" if self._camoufox_ready() else "skip"
        if primary == "camoufox":
            return "nodriver" if self._nodriver_ready() else "skip"
        return "skip"

    # Choose the initial engine for a URL.
    def _choose_engine(self, url: str, method_hint: Optional[str] = None) -> str:
        """Pick the best engine based on hints, registry rules, and availability."""

        hint = (method_hint or "").strip().lower()
        if hint in {"http", "xml_feed", "json_api", "official_api", "skip"}:
            return "skip"
        if hint == "camoufox":
            if self._camoufox_ready():
                return "camoufox"
            if self._nodriver_ready():
                return "nodriver"
            return "skip"
        if hint == "nodriver":
            if self._nodriver_ready():
                return "nodriver"
            if self._camoufox_ready():
                return "camoufox"
            return "skip"
        if hint in {"stealth", "browser"}:
            if self._camoufox_ready():
                return "camoufox"
            if self._nodriver_ready():
                return "nodriver"
            return "skip"

        reg = get_registry()
        if reg.is_friendly(url) or reg.should_skip(url):
            return "skip"
        if reg.needs_camoufox(url) and self._camoufox_ready():
            return "camoufox"
        if self._prefer_camoufox and self._camoufox_ready():
            return "camoufox"
        if self._camoufox_ready():
            return "camoufox"
        if self._nodriver_ready():
            return "nodriver"
        return "skip"

    # Extract one page with fallback support.
    async def extract(self, url: str, method_hint: Optional[str] = None) -> StealthResult:
        """Run stealth extraction for one URL."""

        engine = self._choose_engine(url, method_hint=method_hint)

        if engine == "skip":
            self._stats["skipped_lightweight"] += 1
            return StealthResult(
                url=url,
                method="skip",
                success=False,
                error="Stealth not required for selected method/domain",
            )

        t0 = time.time()
        proxy_url = None
        if self._proxy_rotator:
            proxy_url = self._proxy_rotator.get_proxy_for_url(url)

        result = await self._try_engine(engine, url, proxy_url)
        if result and result.success:
            latency = (time.time() - t0) * 1000
            result.latency_ms = latency
            if self._proxy_rotator and proxy_url:
                self._proxy_rotator.report_success(proxy_url, latency)
            return result

        fallback_engine = self._fallback_engine(engine)
        if fallback_engine != "skip":
            result = await self._try_engine(fallback_engine, url, proxy_url)
            if result and result.success:
                latency = (time.time() - t0) * 1000
                result.latency_ms = latency
                if self._proxy_rotator and proxy_url:
                    self._proxy_rotator.report_success(proxy_url, latency)
                return result

        if self._proxy_rotator and proxy_url:
            self._proxy_rotator.report_failure(proxy_url)

        return StealthResult(
            url=url,
            method=f"{engine}+{fallback_engine}",
            success=False,
            latency_ms=(time.time() - t0) * 1000,
            error="Both engines failed",
        )

    # Run one engine attempt.
    async def _try_engine(
        self,
        engine_name: str,
        url: str,
        proxy_url: Optional[str] = None,
    ) -> Optional[StealthResult]:
        """Execute one engine and normalize its result."""

        try:
            raw: Optional[Dict] = None

            if engine_name == "nodriver" and self._nodriver_ready():
                if proxy_url:
                    self._nodriver.proxy = proxy_url
                raw = await self._nodriver.extract(url)

            elif engine_name == "camoufox" and self._camoufox_ready():
                if proxy_url and self._proxy_rotator:
                    domain = _extract_domain(url)
                    self._camoufox.proxy = self._proxy_rotator.get_camoufox_proxy(domain)
                raw = await self._camoufox.extract(url)

            if raw and raw.get("html"):
                self._stats[f"{engine_name}_success"] += 1
                return StealthResult(
                    url=url,
                    html=raw["html"],
                    method=engine_name,
                    success=True,
                )

            self._stats[f"{engine_name}_fail"] += 1
            return None

        except Exception as exc:
            self._stats[f"{engine_name}_fail"] += 1
            logger.warning("%s failed for %s: %s", engine_name, url, exc)
            return None

    # Extract a batch of URLs.
    async def extract_batch(self, urls: List[str]) -> List[StealthResult]:
        """Run stealth extraction for multiple URLs."""

        results = await self._dispatcher.run(urls, self.extract)
        return [
            r if r else StealthResult(url=urls[i], success=False, error="dispatcher_error")
            for i, r in enumerate(results)
        ]

    # Expose runtime pool statistics.
    def get_stats(self) -> Dict:
        """Return current pool and proxy statistics."""

        stats = dict(self._stats)
        stats["nodriver_enabled"] = self._enable_nodriver
        stats["camoufox_enabled"] = self._enable_camoufox
        stats["nodriver_available"] = self._nodriver_ready()
        stats["camoufox_available"] = self._camoufox_ready()
        stats["proxy_count"] = self._proxy_rotator.proxy_count if self._proxy_rotator else 0
        stats["active_tasks"] = self._dispatcher.active_tasks
        if self._proxy_rotator:
            stats["proxy_stats"] = self._proxy_rotator.get_stats()
        return stats
