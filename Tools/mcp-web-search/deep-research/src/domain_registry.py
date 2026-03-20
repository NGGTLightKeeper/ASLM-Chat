# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    from .endpoint_overlay import EndpointStrategy, get_endpoint_overlay, normalize_domain
except (ImportError, ValueError):
    from endpoint_overlay import EndpointStrategy, get_endpoint_overlay, normalize_domain  # type: ignore

logger = logging.getLogger("background_agent.domain_registry")

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
    def choose_method(self, url_or_domain: str, method_hint: Optional[str] = None) -> str:
        """Choose the final access method, honoring explicit hints when present."""

        hint = (method_hint or "").strip().lower()
        if hint and hint != "auto":
            return hint
        return self.resolve_access_strategy(url_or_domain).method

    # Strategy helpers.
    def get_rate_limit(self, url_or_domain: str) -> Tuple[float, int]:
        """Return the configured requests-per-second and burst values."""

        info = self.lookup(url_or_domain)
        return info.rps, info.burst

    # Strategy helpers.
    def should_skip(self, url_or_domain: str) -> bool:
        """Return whether the domain is marked as non-fetchable."""

        info = self.lookup(url_or_domain)
        return info.method == "skip"

    # Strategy helpers.
    def is_friendly(self, url_or_domain: str) -> bool:
        """Return whether the domain belongs to the friendly tier."""

        return self.lookup(url_or_domain).tier == "friendly"

    # Strategy helpers.
    def needs_stealth(self, url_or_domain: str) -> bool:
        """Return whether the domain requires a stealth browser."""

        info = self.lookup(url_or_domain)
        return info.method in ("nodriver", "camoufox")

    # Strategy helpers.
    def needs_camoufox(self, url_or_domain: str) -> bool:
        """Return whether the domain specifically prefers Camoufox."""

        return self.lookup(url_or_domain).method == "camoufox"

    # Strategy helpers.
    def get_feed_url(self, url_or_domain: str) -> Optional[str]:
        """Return the best known feed URL for a domain or URL."""

        strategy = self.resolve_access_strategy(url_or_domain)
        if strategy.source == "overlay":
            return strategy.endpoint_url or strategy.rewritten_url or None
        return self._lookup_static(url_or_domain).feed_prefix

    # Strategy helpers.
    def get_json_api_hint(self, url_or_domain: str) -> Optional[str]:
        """Return the static JSON API hint for a domain, if configured."""

        return self._lookup_static(url_or_domain).json_api_hint

    # Strategy helpers.
    def get_seed_urls(self, url_or_domain: str) -> List[str]:
        """Return deduplicated seed URLs from overlay and static registry data."""

        strategy = self.resolve_access_strategy(url_or_domain)
        items = list(strategy.seed_urls)
        static_feed = self._lookup_static(url_or_domain).feed_prefix
        if static_feed:
            items.append(static_feed)
        deduped: List[str] = []
        seen = set()
        for item in items:
            if not item or item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    # Topic helpers.
    @staticmethod
    # Map a query type to a registry topic.
    def topic_from_query_type(query_type: str) -> str:
        """Map a research query type into the registry topic namespace."""

        mapping = {
            "technical": "tech",
            "academic": "academic",
            "medical": "medical",
            "finance": "finance",
            "journalistic": "news",
            "shopping": "shopping",
            "general": "general",
        }
        return mapping.get((query_type or "").strip().lower(), "general")

    # Topic helpers.
    def get_topic_domains(self, topic: str, include_general: bool = True) -> List[str]:
        """Return all domains that belong to the given topic bucket."""

        normalized = (topic or "general").strip().lower()
        results: List[str] = []
        seen: set[int] = set()
        for info in self._domains.values():
            marker = id(info)
            if marker in seen:
                continue
            seen.add(marker)
            topic_match = normalized in info.topics
            general_match = include_general and "general" in info.topics
            if topic_match or general_match:
                results.append(info.pattern)
        return results

    # Topic helpers.
    def rank_domains_for_topic(
        self,
        topic: str,
        limit: Optional[int] = None,
        domain_performance=None,
    ) -> List[str]:
        """Rank domains for a topic using trust, method, and performance signals."""

        normalized = (topic or "general").strip().lower()
        candidates: List[Tuple[float, str]] = []

        tier_weight = {
            "friendly": 1.0,
            "moderate": 0.75,
            "hardened": 0.45,
            "fortress": 0.05,
            "unknown": 0.50,
        }
        method_weight = {
            "http": 0.55,
            "xml_feed": 0.85,
            "json_api": 0.85,
            "official_api": 0.95,
            "nodriver": 0.35,
            "camoufox": 0.30,
            "skip": -0.5,
        }

        seen: set[int] = set()
        for info in self._domains.values():
            marker = id(info)
            if marker in seen:
                continue
            seen.add(marker)

            if normalized not in info.topics and "general" not in info.topics:
                continue
            if info.method == "skip":
                continue

            perf_score = 0.5
            if domain_performance is not None:
                try:
                    perf_score = float(domain_performance.get_weighted_score(info.pattern))
                except Exception:
                    perf_score = 0.5

            topic_bonus = 0.20 if normalized in info.topics else 0.0
            trust_component = tier_weight.get(info.tier, 0.5)
            method_component = method_weight.get(info.method, 0.2)

            score = (trust_component * 0.45) + (method_component * 0.20) + (perf_score * 0.35) + topic_bonus
            candidates.append((score, info.pattern))

        candidates.sort(key=lambda x: x[0], reverse=True)
        ranked = [domain for _, domain in candidates]
        if limit is not None:
            return ranked[: max(0, int(limit))]
        return ranked

    # Integration helpers.
    def build_rate_limiter_overrides(self) -> Dict[str, float]:
        """Build per-domain rate-limit overrides for the crawler."""

        overrides: Dict[str, float] = {}
        seen: set[int] = set()
        for info in self._domains.values():
            marker = id(info)
            if marker in seen:
                continue
            seen.add(marker)
            if info.rps > 0:
                overrides[info.pattern] = info.rps
        return overrides

    # Integration helpers.
    def build_pool_routing(self) -> Dict[str, str]:
        """Build browser-pool routing rules from the registry methods."""

        routing: Dict[str, str] = {}
        seen: set[int] = set()
        for info in self._domains.values():
            marker = id(info)
            if marker in seen:
                continue
            seen.add(marker)

            if info.method == "camoufox":
                routing[info.pattern] = "camoufox"
            elif info.method == "nodriver":
                routing[info.pattern] = "nodriver"
            elif info.method in ("http", "xml_feed", "json_api", "official_api"):
                routing[info.pattern] = "skip"
            elif info.method == "skip":
                routing[info.pattern] = "skip"
        return routing

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

    # Reporting helpers.
    @property
    # Return the number of unique domain entries.
    def domain_count(self) -> int:
        """Return the number of unique domain entries in the registry."""

        return len({id(v) for v in self._domains.values()})


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
