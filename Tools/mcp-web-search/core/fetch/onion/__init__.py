# Copyright NEXTGGTECH. Elastic License 2.0.

"""Optional Tor/onion access layer.

Strictly opt-in and zero-install: nothing here bundles or installs tor. When the `tor`
config section is enabled it reuses a running tor SOCKS (system daemon or an open Tor
Browser) and only spawns its own from an already-installed tor binary it can discover. No
tor available → every entry point degrades to a no-op, never an error.

The allowlist is static and hand-vetted (the seed registry); there is no runtime onion
discovery or persistence.
"""

from .models import OnionService
from .registry import load_seed_services, load_services, service_for, services_in
from .resolver import resolve_all, resolve_onion
from .transport import OnionFetch, onion_available, onion_fetch

__all__ = [
    "OnionFetch", "OnionService", "onion_available", "onion_fetch",
    "load_services", "load_seed_services", "service_for", "services_in",
    "resolve_onion", "resolve_all",
]
