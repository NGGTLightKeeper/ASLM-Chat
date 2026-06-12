# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

# Pass-through custom-domain layer with a single API (see base.py). read_page asks
# match(url) for a handler and calls handler.read(url, ctx). Order matters only in that
# the first matching handler wins; the host tests below do not overlap.
#
# Domains needing only a forced fetch method (twitch/flashscore/sofascore → camoufox,
# cursor → nextjs_rsc, citilink → camoufox) are NOT handlers — read_page's generic
# pipeline picks that up from core.profiles.known_domains. Only domains with bespoke
# fetching (terminal APIs) or URL-variant logic (dns-shop) get a handler here.

from custom_domains.base import (
    DomainHandler,
    FetchContext,
    GenericRequest,
    PageAttempt,
    PageResult,
)
from custom_domains.amazon import HANDLER as _amazon
from custom_domains.dns_shop import HANDLER as _dns_shop
from custom_domains.ebay import HANDLER as _ebay
from custom_domains.github import HANDLER as _github
from custom_domains.reddit import HANDLER as _reddit
from custom_domains.stackexchange import HANDLER as _stackexchange
from custom_domains.x import HANDLER as _x
from custom_domains.youtube import HANDLER as _youtube

HANDLERS: list[DomainHandler] = [
    _github,
    _reddit,
    _x,
    _stackexchange,
    _youtube,
    _amazon,
    _ebay,
    _dns_shop,
]


# Return the first custom-domain handler matching the URL, or None for generic handling.
def match(url: str) -> DomainHandler | None:
    for handler in HANDLERS:
        try:
            if handler.matches(url):
                return handler
        except Exception:
            continue
    return None


__all__ = [
    "DomainHandler",
    "FetchContext",
    "GenericRequest",
    "HANDLERS",
    "PageAttempt",
    "PageResult",
    "match",
]
