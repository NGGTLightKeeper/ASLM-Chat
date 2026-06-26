# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


# One vetted onion service from the registry seed. `onion` is the last-known address
# (seed/fallback); the resolver refreshes it from `clearnet_anchor`'s Onion-Location.
@dataclass(frozen=True, slots=True)
class OnionService:
    name: str
    category: str          # media / infosec / rights / privacy_mail / whistleblow / archive
    clearnet_anchor: str   # TLS https URL that authoritatively publishes the onion
    onion: str             # seeded onion URL (fallback when refresh fails)

    # The .onion host of the seeded address (for logging / source_domain).
    @property
    def onion_host(self) -> str:
        return (urlparse(self.onion).netloc or "").lower()
