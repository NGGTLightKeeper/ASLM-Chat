# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import urlparse

from .endpoint_overlay import EndpointStrategy, get_endpoint_overlay, normalize_domain

logger = logging.getLogger("core.registry.domain_registry")

# Domain metadata models.
# Static domain metadata record.
@dataclass
class DomainInfo:
    pattern: str
    tier: str = "unknown"  # friendly / moderate / hardened / fortress
    method: str = "http"  # http / xml_feed / json_api / nodriver / camoufox / official_api / skip
    rps: float = 1.0
    burst: int = 3
    aliases: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    feed_prefix: Optional[str] = None
    json_api_hint: Optional[str] = None
    official_api: Optional[str] = None
    waf: Optional[str] = None
    rate_limit_headers: List[str] = field(default_factory=list)
    notes: str = ""
    response_time_ms: Optional[int] = None  # measured p95 latency from bench_domains.py
    try_preview_bot: bool = False  # try social-media bot UA probe (Telegrambot, WhatsApp, etc.)

# Access strategy models.
# Resolved access strategy record.
@dataclass
class AccessStrategy:
    source: str = "default"
    method: str = "http"
    domain: str = ""
    tier: str = "unknown"
    endpoint_url: str = ""
    rewritten_url: str = ""
    scope: str = "domain"
    path_pattern: str = ""
    transform_kind: str = ""
    seed_urls: List[str] = field(default_factory=list)
    method_hint: str = "http"
    response_time_ms: Optional[int] = None  # per-domain measured latency (ms); None = use global default


_DEFAULT_INFO = DomainInfo(
    pattern="*",
    tier="unknown",
    method="http",
    rps=1.0,
    burst=3,
    topics=["general"],
    notes="Unknown domain - default settings",
)

# Registry implementation.
class DomainRegistry:
    """Resolve domain metadata from the static registry and dynamic overlay."""

    # Construction helpers.
    def __init__(self, config_path: Optional[str] = None):
        """Load the registry file and build the in-memory lookup table."""

        self._domains: Dict[str, DomainInfo] = {}
        self._loaded = False

        if config_path is None:
            here = os.path.dirname(os.path.abspath(__file__))
            candidates = [
                os.path.join(here, "domain_registry.json"),
                os.path.join(here, "config", "domain_registry.json"),
                os.path.join(here, "..", "config", "domain_registry.json"),
                os.path.join(here, "..", "domain_registry.json"),
            ]
            for candidate in candidates:
                if os.path.exists(candidate):
                    config_path = candidate
                    break

        if config_path and os.path.exists(config_path):
            self._load(config_path)
        else:
            logger.warning("domain_registry.json not found - using empty registry")

    # Loading helpers.
    def _load(self, path: str) -> None:
        """Load registry entries from JSON and normalize them for lookup."""

        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            for entry in data.get("domains", []):
                if "_section" in entry:
                    continue

                pattern = entry.get("pattern", "").strip().lower()
                if not pattern:
                    continue

                topics = entry.get("topics") or []
                if not isinstance(topics, list):
                    topics = []

                info = DomainInfo(
                    pattern=pattern,
                    tier=(entry.get("tier") or "unknown").lower(),
                    method=(entry.get("method") or "http").lower(),
                    rps=float(entry.get("rps", 1.0) or 0.0),
                    burst=int(entry.get("burst", 3) or 0),
                    aliases=[a.lower() for a in (entry.get("aliases") or [])],
                    topics=[str(t).lower() for t in topics if str(t).strip()],
                    feed_prefix=entry.get("feed_prefix"),
                    json_api_hint=entry.get("json_api_hint"),
                    official_api=entry.get("official_api"),
                    waf=entry.get("waf"),
                    rate_limit_headers=entry.get("rate_limit_headers") or [],
                    notes=entry.get("notes") or "",
                    response_time_ms=int(v) if (v := entry.get("response_time_ms")) is not None else None,
                    try_preview_bot=bool(entry.get("try_preview_bot", False)),
                )
                if not info.topics:
                    info.topics = ["general"]

                self._domains[pattern] = info
                for alias in info.aliases:
                    self._domains[alias] = info

            self._loaded = True
            logger.info(
                "DomainRegistry loaded: %s entries from %s",
                len(data.get("domains", [])),
                path,
            )
        except Exception as exc:
            logger.error("Failed to load domain registry: %s", exc)

    # Lookup helpers.
    def _extract_domain(self, url_or_domain: str) -> str:
        """Normalize a URL or domain string into the bare lookup key."""

        return normalize_domain(url_or_domain)

    # Lookup helpers.
    def _lookup_static(self, url_or_domain: str) -> DomainInfo:
        """Resolve domain metadata from the static registry only."""

        domain = self._extract_domain(url_or_domain)
        if not domain:
            return _DEFAULT_INFO

        if domain in self._domains:
            return self._domains[domain]

        parts = domain.split(".")
        for i in range(1, len(parts)):
            parent = ".".join(parts[i:])
            if parent in self._domains:
                return self._domains[parent]

        return _DEFAULT_INFO

    # Lookup helpers.
    def _overlay_to_info(self, url_or_domain: str, overlay: EndpointStrategy) -> DomainInfo:
        """Merge an overlay strategy with static registry defaults."""

        static_info = self._lookup_static(url_or_domain)
        return DomainInfo(
            pattern=overlay.domain,
            tier=static_info.tier,
            method=overlay.method,
            rps=static_info.rps,
            burst=static_info.burst,
            aliases=list(static_info.aliases),
            topics=list(static_info.topics),
            feed_prefix=static_info.feed_prefix,
            json_api_hint=static_info.json_api_hint,
            official_api=static_info.official_api,
            waf=static_info.waf,
            rate_limit_headers=list(static_info.rate_limit_headers),
            notes=static_info.notes,
            response_time_ms=static_info.response_time_ms,
            try_preview_bot=static_info.try_preview_bot,
        )

    # Lookup helpers.
    def lookup(self, url_or_domain: str) -> DomainInfo:
        """Resolve domain metadata with overlay strategies taking precedence."""

        overlay = get_endpoint_overlay().lookup_validated(self._extract_domain(url_or_domain), url_or_domain)
        if overlay is not None:
            return self._overlay_to_info(url_or_domain, overlay)
        return self._lookup_static(url_or_domain)

    # Strategy helpers.
    def resolve_access_strategy(self, url_or_domain: str) -> AccessStrategy:
        """Build the effective access strategy for a URL or domain."""

        domain = self._extract_domain(url_or_domain)
        overlay = get_endpoint_overlay().lookup_validated(domain, url_or_domain)
        if overlay is not None:
            return AccessStrategy(
                source="overlay",
                method=overlay.method,
                domain=overlay.domain,
                tier=self._lookup_static(url_or_domain).tier,
                endpoint_url=overlay.endpoint_url,
                rewritten_url=overlay.rewritten_url,
                scope=overlay.scope,
                path_pattern=overlay.path_pattern,
                transform_kind=overlay.transform_kind,
                seed_urls=get_endpoint_overlay().get_validated_seed_urls(domain) if overlay.is_seed_only else [],
                method_hint=overlay.method,
            )

        info = self._lookup_static(url_or_domain)
        rewritten = ""
        seed_urls: List[str] = []
        if info.feed_prefix and "://" in (url_or_domain or ""):
            rewritten = info.feed_prefix + urlparse(url_or_domain).path
        elif info.feed_prefix:
            seed_urls = [info.feed_prefix]
        return AccessStrategy(
            source="static" if info.pattern != "*" else "default",
            method=info.method,
            domain=domain,
            tier=info.tier,
            endpoint_url=info.feed_prefix or info.official_api or "",
            rewritten_url=rewritten,
            scope="domain",
            path_pattern="",
            transform_kind="",
            seed_urls=seed_urls,
            method_hint=info.method,
            response_time_ms=info.response_time_ms,
        )

    # Strategy helpers.
    def needs_camoufox(self, url_or_domain: str) -> bool:
        """Return whether the domain specifically prefers Camoufox."""

        return self.lookup(url_or_domain).method == "camoufox"

    # Reporting helpers.
    def summary(self) -> Dict[str, List[str]]:
        """Return a compact summary grouped by trust tier."""

        result: Dict[str, List[str]] = {
            "friendly": [],
            "moderate": [],
            "hardened": [],
            "fortress": [],
            "unknown": [],
        }
        seen: set[int] = set()
        for info in self._domains.values():
            marker = id(info)
            if marker in seen:
                continue
            seen.add(marker)
            tier = info.tier if info.tier in result else "unknown"
            result[tier].append(f"{info.pattern} [{info.method}] ({','.join(info.topics)})")
        return result

    # Reporting helpers.
    @property
    # Return whether the registry loaded successfully.
    def loaded(self) -> bool:
        """Return whether the registry file was loaded successfully."""

        return self._loaded


_registry: Optional[DomainRegistry] = None

# Singleton access helpers.
def get_registry(config_path: Optional[str] = None) -> DomainRegistry:
    """Return the shared domain-registry instance."""

    global _registry
    if _registry is None:
        _registry = DomainRegistry(config_path)
    return _registry

# Lazy proxy helpers.
class _RegistryProxy:
    """Proxy attribute access to the shared registry instance."""

    # Proxy helpers.
    def __getattr__(self, item):
        """Forward attribute access to the shared registry."""

        return getattr(get_registry(), item)


registry = _RegistryProxy()
