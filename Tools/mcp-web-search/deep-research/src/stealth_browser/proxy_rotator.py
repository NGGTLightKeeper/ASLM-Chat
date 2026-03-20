# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import logging
import random
import time
from dataclasses import dataclass
from threading import Lock
from typing import Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger("stealth.proxy")


# Proxy statistics models.
# Proxy runtime statistics.
@dataclass
class ProxyStats:
    url: str
    success_count: int = 0
    fail_count: int = 0
    total_latency_ms: float = 0.0
    last_used: float = 0.0
    last_fail: float = 0.0
    blocked_until: float = 0.0

    # Compute the success ratio.
    @property
    def reliability(self) -> float:
        """Return a simple success ratio in the range 0..1."""

        total = self.success_count + self.fail_count
        if total == 0:
            return 0.5
        return self.success_count / total

    # Compute the average successful latency.
    @property
    def avg_latency_ms(self) -> float:
        """Return the average successful latency, or a large fallback value."""

        if self.success_count == 0:
            return 999.0
        return self.total_latency_ms / self.success_count

    # Compute the weighted selection score.
    @property
    def weight(self) -> float:
        """Return the weighted random-selection score for this proxy."""

        latency_factor = 1.0 / (1.0 + self.avg_latency_ms / 1000.0)
        return max(self.reliability * latency_factor, 0.01)


# Proxy rotation manager.
# Proxy rotation and cooldown manager.
class ProxyRotator:
    # Configure the proxy pool.
    def __init__(
        self,
        proxies: List[str],
        cooldown_on_fail_sec: float = 300.0,
        session_sticky: bool = True,
    ):
        self._lock = Lock()
        self._proxies: Dict[str, ProxyStats] = {}
        self._session_map: Dict[str, str] = {}
        self._cooldown = cooldown_on_fail_sec
        self._sticky = session_sticky

        for proxy_url in proxies:
            self._proxies[proxy_url] = ProxyStats(url=proxy_url)

    # Expose the configured proxy count.
    @property
    def proxy_count(self) -> int:
        """Return the number of configured proxies."""

        return len(self._proxies)

    # Collect proxies that are currently usable.
    def _alive_proxies(self) -> List[ProxyStats]:
        """Return proxies that are not currently in cooldown."""

        now = time.time()
        return [
            stats
            for stats in self._proxies.values()
            if now >= stats.blocked_until
        ]

    # Pick a proxy for a domain or generic request.
    def get_proxy(self, domain: Optional[str] = None) -> Optional[str]:
        """Pick a proxy, optionally reusing the same one for a domain."""

        with self._lock:
            if not self._proxies:
                return None

            if self._sticky and domain:
                existing = self._session_map.get(domain)
                if existing and existing in self._proxies:
                    stats = self._proxies[existing]
                    if time.time() >= stats.blocked_until:
                        stats.last_used = time.time()
                        return existing

            alive = self._alive_proxies()
            if not alive:
                alive = list(self._proxies.values())

            weights = [stats.weight for stats in alive]
            chosen = random.choices(alive, weights=weights, k=1)[0]
            chosen.last_used = time.time()

            if self._sticky and domain:
                self._session_map[domain] = chosen.url

            return chosen.url

    # Pick a proxy based on a URL.
    def get_proxy_for_url(self, url: str) -> Optional[str]:
        """Resolve a domain from the URL and return a matching proxy."""

        domain = urlparse(url).netloc.lower()
        return self.get_proxy(domain)

    # Record a successful proxy request.
    def report_success(self, proxy_url: str, latency_ms: float = 0.0) -> None:
        """Record a successful proxy usage event."""

        with self._lock:
            stats = self._proxies.get(proxy_url)
            if stats:
                stats.success_count += 1
                stats.total_latency_ms += latency_ms

    # Record a failed proxy request.
    def report_failure(self, proxy_url: str) -> None:
        """Record a failure and apply cooldown to weak proxies."""

        with self._lock:
            stats = self._proxies.get(proxy_url)
            if stats:
                stats.fail_count += 1
                stats.last_fail = time.time()
                if stats.reliability < 0.3:
                    stats.blocked_until = time.time() + self._cooldown
                    logger.info(
                        f"Proxy {proxy_url} blocked for {self._cooldown}s "
                        f"(reliability={stats.reliability:.2f})"
                    )

    # Clear sticky proxy state for a domain.
    def clear_session(self, domain: str) -> None:
        """Drop any sticky proxy assignment for the domain."""

        with self._lock:
            self._session_map.pop(domain, None)

    # Return diagnostic proxy statistics.
    def get_stats(self) -> List[Dict]:
        """Return per-proxy statistics for diagnostics."""

        with self._lock:
            return [
                {
                    "url": stats.url,
                    "reliability": round(stats.reliability, 3),
                    "avg_latency_ms": round(stats.avg_latency_ms, 1),
                    "weight": round(stats.weight, 3),
                    "success": stats.success_count,
                    "fail": stats.fail_count,
                    "blocked": time.time() < stats.blocked_until,
                }
                for stats in self._proxies.values()
            ]

    # Convert a proxy URL into Camoufox settings.
    def get_camoufox_proxy(self, domain: Optional[str] = None) -> Optional[dict]:
        """Return a proxy mapping formatted for Camoufox."""

        proxy_url = self.get_proxy(domain)
        if not proxy_url:
            return None

        parsed = urlparse(proxy_url)
        scheme = parsed.scheme or "http"
        host = parsed.hostname
        if not host:
            return None

        port = parsed.port or (1080 if scheme.startswith("socks") else 8080)
        result = {"server": f"{scheme}://{host}:{port}"}
        if parsed.username:
            result["username"] = parsed.username
        if parsed.password:
            result["password"] = parsed.password
        return result
