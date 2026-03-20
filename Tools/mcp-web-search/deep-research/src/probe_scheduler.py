# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
from typing import Iterable, Optional

import aiohttp

from src.config import ResearchConfig
from src.endpoint_overlay import ProbeCandidate, get_endpoint_overlay, normalize_domain, validate_candidate_payload
from src.extractor import DEFAULT_HTTP_HEADERS
from src.models import ExtractedSource, ResearchState, SearchResult

try:
    from src.domain_registry import get_registry as _get_registry

    _DOMAIN_REGISTRY = _get_registry()
except Exception:
    _DOMAIN_REGISTRY = None  # type: ignore


# Endpoint discovery scheduler.
class EndpointProbeScheduler:
    """Run background endpoint validation tasks without blocking the main flow."""

    # Construction helpers.
    def __init__(self, state: ResearchState) -> None:
        """Capture runtime settings and initialize lazy scheduler state."""

        self.state = state
        self.cfg: ResearchConfig = state.config
        self.enabled = bool(getattr(self.cfg, "endpoint_discovery_enabled", False))
        self.max_domains = max(
            1,
            int(getattr(self.cfg, "endpoint_discovery_max_domains_per_run", 12)),
        )
        self.overlay = get_endpoint_overlay(
            getattr(self.cfg, "discovered_endpoints_db", None)
        )
        self.timeout = max(
            2.0,
            float(getattr(self.cfg, "endpoint_probe_timeout", 6.0)),
        )
        self._sem = asyncio.Semaphore(
            max(1, int(getattr(self.cfg, "endpoint_probe_concurrency", 4)))
        )
        self._scheduled_domains: dict[str, str] = {}
        self._tasks: list[asyncio.Task] = []
        self._session: Optional[aiohttp.ClientSession] = None


    # Session management.
    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Create the shared HTTP session on first use."""

        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                headers=DEFAULT_HTTP_HEADERS,
                timeout=timeout,
            )

        return self._session


    # Candidate collection.
    def _collect_candidates(self, urls: Iterable[str]) -> list[tuple[str, str]]:
        """Pick one representative URL per domain up to the configured cap."""

        candidates: list[tuple[str, str]] = []
        for raw_url in urls:
            url = str(raw_url or "").strip()
            if not url or "://" not in url:
                continue

            domain = normalize_domain(url)
            if not domain or domain in self._scheduled_domains:
                continue
            if _DOMAIN_REGISTRY is not None and _DOMAIN_REGISTRY.should_skip(domain):
                continue
            if len(self._scheduled_domains) >= self.max_domains:
                break

            self._scheduled_domains[domain] = url
            candidates.append((domain, url))

        return candidates


    # Public enqueue API.
    def enqueue_urls(self, urls: Iterable[str]) -> None:
        """Schedule probing tasks for a sequence of URLs."""

        if not self.enabled:
            return

        for domain, sample_url in self._collect_candidates(urls):
            self._tasks.append(
                asyncio.create_task(self._probe_domain(domain, sample_url))
            )

    # Public enqueue API.
    def enqueue_results(self, results: Iterable[SearchResult]) -> None:
        """Schedule probing for search-result URLs."""

        self.enqueue_urls(getattr(result, "url", "") for result in results)

    # Public enqueue API.
    def enqueue_sources(self, sources: Iterable[ExtractedSource]) -> None:
        """Schedule probing for extracted-source URLs."""

        self.enqueue_urls(getattr(source, "url", "") for source in sources)


    # Probe internals.
    async def _fetch_candidate(self, candidate: ProbeCandidate) -> Optional[dict]:
        """Fetch a candidate endpoint and validate the returned payload."""

        session = await self._ensure_session()
        async with self._sem:
            try:
                async with session.get(candidate.endpoint_url, allow_redirects=True) as response:
                    text = await response.text(errors="ignore")
                    return validate_candidate_payload(
                        candidate=candidate,
                        status=response.status,
                        content_type=response.headers.get("Content-Type", ""),
                        body=text,
                    )
            except Exception:
                return None

    # Probe internals.
    async def _probe_domain(self, domain: str, sample_url: str) -> None:
        """Probe all due candidates for one domain and persist their outcomes."""

        try:
            self.state.log(f"endpoint_probe_started: {domain}")
            candidates = self.overlay.get_due_candidates(domain, sample_url=sample_url)
            if not candidates:
                return

            for candidate in candidates:
                before = self.overlay.get_entry(candidate)
                payload = await self._fetch_candidate(candidate)

                if payload is None:
                    self.overlay.record_probe_result(
                        domain,
                        candidate,
                        success=False,
                        metadata={"http_status": 0},
                    )
                    continue

                # Robots discovery can fan out into concrete sitemap candidates.
                if candidate.endpoint_type == "robots":
                    for sitemap_url in payload.get("sitemaps", [])[:3]:
                        sitemap_candidate = ProbeCandidate(
                            domain=domain,
                            endpoint_url=sitemap_url,
                            endpoint_type="sitemap",
                            scope="domain",
                            discovered_from_url=sample_url,
                        )
                        sitemap_before = self.overlay.get_entry(sitemap_candidate)
                        sitemap_payload = await self._fetch_candidate(sitemap_candidate)
                        if sitemap_payload is None:
                            continue

                        self.overlay.record_probe_result(
                            domain,
                            sitemap_candidate,
                            success=True,
                            metadata=sitemap_payload,
                        )
                        sitemap_after = self.overlay.get_entry(sitemap_candidate)
                        self.state.log(
                            f"endpoint_probe_validated: {domain} -> "
                            f"{sitemap_candidate.endpoint_url}"
                        )
                        if (sitemap_before or {}).get("status") != "validated" and (
                            sitemap_after or {}
                        ).get("status") == "validated":
                            self.state.log(
                                f"endpoint_probe_promoted: {domain} -> "
                                f"{sitemap_candidate.endpoint_url}"
                            )
                    continue

                self.overlay.record_probe_result(
                    domain,
                    candidate,
                    success=True,
                    metadata=payload,
                )
                after = self.overlay.get_entry(candidate)
                self.state.log(
                    f"endpoint_probe_validated: {domain} -> {candidate.endpoint_url}"
                )
                if (before or {}).get("status") != "validated" and (
                    after or {}
                ).get("status") == "validated":
                    self.state.log(
                        f"endpoint_probe_promoted: {domain} -> {candidate.endpoint_url}"
                    )
        except Exception as exc:
            self.state.log(f"  endpoint_probe_error: {domain} -> {exc}")


    # Teardown helpers.
    async def finalize(self) -> None:
        """Await all pending probe tasks and close the HTTP session."""

        if not self._tasks:
            if self._session and not self._session.closed:
                await self._session.close()
            return

        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
