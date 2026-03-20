# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger("background_agent.robots")


# Cached robots entries.
# Cached robots.txt state for one domain.
@dataclass
class _RobotsEntry:
    """Cached robots.txt entry for a single domain."""

    parser: RobotFileParser
    fetched_at: float
    crawl_delay: Optional[float] = None
    fetch_error: bool = False


# Robots checker.
# robots.txt access checker.
class RobotsChecker:
    # Configure robots.txt handling.
    def __init__(
        self,
        user_agent: str = "MCP-WebSearch/1.0",
        cache_ttl: int = 3600,
        respect_robots: bool = True,
        default_crawl_delay: float = 1.0,
    ):
        self.user_agent = user_agent
        self.cache_ttl = cache_ttl
        self.respect_robots = respect_robots
        self.default_crawl_delay = default_crawl_delay
        self._cache: Dict[str, _RobotsEntry] = {}
        self._lock = asyncio.Lock()
        self._stats = {
            "checks": 0,
            "allowed": 0,
            "disallowed": 0,
            "fetch_errors": 0,
        }

    # Build the robots.txt URL.
    def _get_robots_url(self, url: str) -> str:
        """Build the robots.txt URL for the URL's domain."""

        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    # Extract the normalized domain.
    def _get_domain(self, url: str) -> str:
        """Return the normalized domain part of a URL."""

        return urlparse(url).netloc.lower()

    # Fetch and parse robots.txt for a domain.
    async def _fetch_robots(self, domain: str, robots_url: str) -> _RobotsEntry:
        """Fetch and parse robots.txt for a single domain."""

        parser = RobotFileParser()
        parser.set_url(robots_url)

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    robots_url,
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers={"User-Agent": self.user_agent},
                ) as response:
                    if response.status == 200:
                        text = await response.text(errors="replace")
                        parser.parse(text.splitlines())

                        crawl_delay = None
                        for line in text.splitlines():
                            line_stripped = line.strip().lower()
                            if line_stripped.startswith("crawl-delay:"):
                                try:
                                    crawl_delay = float(line_stripped.split(":", 1)[1].strip())
                                except (ValueError, IndexError):
                                    pass

                        entry = _RobotsEntry(
                            parser=parser,
                            fetched_at=time.time(),
                            crawl_delay=crawl_delay,
                        )
                        logger.info(f"robots.txt loaded: {domain} (crawl-delay={crawl_delay})")
                        return entry

                    if response.status in (404, 410):
                        parser.allow_all = True
                        return _RobotsEntry(
                            parser=parser,
                            fetched_at=time.time(),
                        )

                    parser.allow_all = True
                    entry = _RobotsEntry(
                        parser=parser,
                        fetched_at=time.time(),
                        fetch_error=True,
                    )
                    self._stats["fetch_errors"] += 1
                    logger.warning(f"robots.txt fetch error {domain}: HTTP {response.status}")
                    return entry
        except Exception as error:
            parser.allow_all = True
            self._stats["fetch_errors"] += 1
            logger.warning(f"robots.txt fetch error {domain}: {error}")
            return _RobotsEntry(
                parser=parser,
                fetched_at=time.time(),
                fetch_error=True,
            )

    # Get a cached or freshly fetched robots entry.
    async def _get_entry(self, url: str) -> _RobotsEntry:
        """Return a cached robots entry or fetch a fresh one."""

        domain = self._get_domain(url)
        async with self._lock:
            entry = self._cache.get(domain)
            if entry and (time.time() - entry.fetched_at) < self.cache_ttl:
                return entry

        robots_url = self._get_robots_url(url)
        entry = await self._fetch_robots(domain, robots_url)
        async with self._lock:
            self._cache[domain] = entry
        return entry

    # Check whether a URL is allowed.
    async def is_allowed(self, url: str) -> bool:
        """Return whether the URL is allowed by robots.txt."""

        self._stats["checks"] += 1

        if not self.respect_robots:
            self._stats["allowed"] += 1
            return True

        try:
            entry = await self._get_entry(url)
            allowed = entry.parser.can_fetch(self.user_agent, url)
            if allowed:
                self._stats["allowed"] += 1
            else:
                self._stats["disallowed"] += 1
                logger.info(f"robots.txt disallows: {url[:80]}")
            return allowed
        except Exception as error:
            logger.debug(f"robots.txt check error for {url}: {error}")
            self._stats["allowed"] += 1
            return True

    # Return the crawl delay for a URL.
    async def crawl_delay(self, url: str) -> float:
        """Return the domain crawl-delay or the configured default."""

        if not self.respect_robots:
            return self.default_crawl_delay

        try:
            entry = await self._get_entry(url)
            if entry.crawl_delay is not None:
                return max(entry.crawl_delay, 0.5)
        except Exception:
            pass
        return self.default_crawl_delay

    # Check a batch of URLs.
    async def is_allowed_batch(self, urls: list) -> Dict[str, bool]:
        """Check a batch of URLs and return a URL-to-bool mapping."""

        results = {}
        for url in urls:
            results[url] = await self.is_allowed(url)
        return results

    # Return robots-check statistics.
    @property
    def stats(self) -> Dict[str, int]:
        """Return robots-check counters."""

        return dict(self._stats)

    # Clear the cached robots data.
    def clear_cache(self):
        """Clear the in-memory robots.txt cache."""

        self._cache.clear()
