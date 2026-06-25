# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Loader for the onion service allowlist (`profiles/seeds/onion_registry.json`).

The seed is the source of truth for *which* onion services are vetted and *where* their
TLS clearnet anchor lives. Mirrors the academic registry: pure load → frozen records, no
I/O beyond reading the JSON. Address freshness is the resolver's job, not the registry's.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from .models import OnionService

logger = logging.getLogger("core.fetch.onion.registry")

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


# All vetted services: the seed bootstrap plus anchored auto-harvested entries from the
# store. NOT cached — the store grows at runtime. Seed wins on a name collision.
def load_services() -> tuple[OnionService, ...]:
    services = {s.name: s for s in load_seed_services()}
    try:
        from .store import get_onion_store

        for s in get_onion_store().list_all():
            services.setdefault(s.name, s)  # seed precedence
    except Exception as exc:  # noqa: BLE001 — store is optional; seed always stands
        logger.debug("onion store unavailable, seed only: %s", exc)
    return tuple(services.values())


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
