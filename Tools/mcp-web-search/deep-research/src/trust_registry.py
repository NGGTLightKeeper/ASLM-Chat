# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import json
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .config import TRUST_REGISTRY_PATH


# Domain matching helpers.
def _is_host_match(host: str, domain: str) -> bool:
    """Return whether a host equals the domain or one of its subdomains."""

    return host == domain or host.endswith("." + domain)


# Registry implementation.
class TrustRegistry:
    """Load trust tiers and blacklist rules from the JSON registry."""

    # Construction helpers.
    def __init__(self, path: Optional[str] = None) -> None:
        """Read the trust registry once and build fast lookup structures."""

        registry_path = Path(path or str(TRUST_REGISTRY_PATH))
        with open(registry_path, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)

        self.tiers: dict[str, dict] = data.get("tiers", {})
        self.domains: list[dict] = data.get("domains", [])
        self.blacklist: dict = data.get("blacklist", {})

        self._lookup: dict[str, dict] = {}
        for entry in self.domains:
            self._lookup[entry["pattern"]] = entry

    # Tier lookup helpers.
    def get_tier(self, url: str) -> Optional[str]:
        """Return the configured trust tier for a URL, if any."""

        netloc = urlparse(url).netloc.lower()
        for pattern, entry in self._lookup.items():
            if netloc == pattern or netloc.endswith("." + pattern):
                return entry["tier"]

        return None

    # Tier lookup helpers.
    def get_weight(self, url: str) -> float:
        """Return the numeric trust weight for a URL."""

        tier = self.get_tier(url)
        if not tier:
            return 0.0

        return self.tiers.get(tier, {}).get("weight", 0.0)


    # Blacklist helpers.
    def is_blacklisted(self, url: str) -> bool:
        """Check URL rules, extensions, and blocked domains."""

        url_lower = url.lower()
        netloc = urlparse(url).netloc.lower()

        for extension in self.blacklist.get("blocked_extensions", []):
            if url_lower.endswith(extension):
                return True

        for blocked_domain in self.blacklist.get("blocked_domain_contains", []):
            if blocked_domain in netloc:
                return True

        # Skip generic URL substring checks for high-trust developer platforms.
        trusted_domains = {
            "github.com",
            "huggingface.co",
            "gitlab.com",
            "arxiv.org",
            "stackoverflow.com",
        }
        if not any(_is_host_match(netloc, domain) for domain in trusted_domains):
            for pattern in self.blacklist.get("blocked_url_patterns", []):
                if pattern in url_lower:
                    return True

        return False

    # Result filtering helpers.
    def filter_results(self, results: list, allowed_tiers: set[str]) -> list:
        """Keep only results whose trust tier is explicitly allowed."""

        filtered = []
        for result in results:
            url = result.url if hasattr(result, "url") else result.get("url", "")
            tier = self.get_tier(url)
            if tier and tier in allowed_tiers:
                filtered.append(result)

        return filtered


# Singleton access helpers.
_instance: Optional[TrustRegistry] = None


# Singleton access helpers.
def get_trust_registry() -> TrustRegistry:
    """Return the shared TrustRegistry instance."""

    global _instance

    if _instance is None:
        _instance = TrustRegistry()

    return _instance
