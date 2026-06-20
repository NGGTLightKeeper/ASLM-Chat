# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from urllib.parse import urlparse

from .models import METHOD_BROWSER, DomainOverride

# Narrow, hand-curated domain knowledge — the only part of the legacy JSON domain
# registry worth carrying over verbatim. Everything else is learned at runtime by
# RuntimeDomainProfiles. These entries are hard overrides (always honoured) and also
# seed the runtime store so read_page never wastes time on a doomed fallback chain.
#
# Source of truth in legacy: core/registry/domain_profiles/*.json (method=browser /
# parsing_mode=nextjs_rsc). Keyed by registrable host without www./m. prefixes.
KNOWN_DOMAINS: dict[str, DomainOverride] = {
    "reddit.com": DomainOverride(required_method=METHOD_BROWSER, note="JSON API blocked; needs browser session"),
    "dns-shop.ru": DomainOverride(required_method=METHOD_BROWSER, note="hardened retail SPA"),
    "citilink.ru": DomainOverride(required_method=METHOD_BROWSER, note="hardened retail SPA"),
    "twitch.tv": DomainOverride(required_method=METHOD_BROWSER, note="JS-gated"),
    "flashscore.com": DomainOverride(required_method=METHOD_BROWSER, note="JS-rendered scores"),
    "sofascore.com": DomainOverride(required_method=METHOD_BROWSER, note="JS-rendered scores"),
    "cursor.com": DomainOverride(parsing_mode="nextjs_rsc", note="Next.js RSC payload"),
}


# Normalise a URL or bare host to a registrable domain (strip scheme, www./m.).
def domain_of(url_or_domain: str) -> str:
    raw = (url_or_domain or "").strip().lower()
    host = urlparse(raw).netloc if "://" in raw else raw
    host = host.split("@")[-1].split(":")[0]
    return host.removeprefix("www.").removeprefix("m.")


# Return the hard override for a URL/host, walking up parent domains, or None.
def get_override(url_or_domain: str) -> DomainOverride | None:
    domain = domain_of(url_or_domain)
    if not domain:
        return None
    if domain in KNOWN_DOMAINS:
        return KNOWN_DOMAINS[domain]
    parts = domain.split(".")
    for i in range(1, len(parts) - 1):
        parent = ".".join(parts[i:])
        if parent in KNOWN_DOMAINS:
            return KNOWN_DOMAINS[parent]
    return None
