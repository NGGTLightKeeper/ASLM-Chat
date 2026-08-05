# Copyright NEXTGGTECH. Elastic License 2.0.

"""Loader for the onion service allowlist (`profiles/seeds/onion_registry.json`).

The seed is the SOLE source of truth for *which* onion services are vetted and *where*
their TLS clearnet anchor lives. The allowlist is static and hand-vetted — there is no
runtime discovery or persistence (the old anchored auto-expansion + `_cache/onion_registry.db`
store were removed: a growable DB on top of a registry whose link-search parser isn't even
finished was more risk than value). Mirrors the academic registry: pure load → frozen
records, no I/O beyond reading the JSON. Address freshness is the resolver's job.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .models import OnionService

_SEED_PATH = Path(__file__).resolve().parents[2] / "profiles" / "seeds" / "onion_registry.json"


# The hand-vetted bootstrap from the JSON seed (immutable → cached).
@lru_cache(maxsize=1)
def load_seed_services() -> tuple[OnionService, ...]:
    try:
        raw = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    out: list[OnionService] = []
    for e in raw.get("services", []):
        if not isinstance(e, dict) or not e.get("name") or not e.get("clearnet_anchor"):
            continue
        out.append(OnionService(
            name=str(e["name"]).strip().lower(),
            category=str(e.get("category") or "other").strip().lower(),
            clearnet_anchor=str(e["clearnet_anchor"]).strip(),
            onion=str(e.get("onion") or "").strip(),
        ))
    return tuple(out)


# All vetted services. The allowlist is exactly the hand-vetted seed — kept as a distinct
# function (not just an alias) so callers have a stable "all services" entry point.
def load_services() -> tuple[OnionService, ...]:
    return load_seed_services()


# Look up one vetted service by name (exact, case-insensitive).
def service_for(name: str) -> OnionService | None:
    n = (name or "").strip().lower()
    for s in load_services():
        if s.name == n:
            return s
    return None


# Services in a given category (e.g. all "media" onions for a news query).
def services_in(category: str) -> tuple[OnionService, ...]:
    c = (category or "").strip().lower()
    return tuple(s for s in load_services() if s.category == c)
