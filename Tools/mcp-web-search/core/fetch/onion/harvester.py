# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Anchored auto-expansion of the onion allowlist.

Scans a curated list of TRUSTED clearnet domains and admits only those that self-publish an
Onion-Location header — so every harvested entry is legitimacy-anchored to the domain's own
TLS cert, never to an onion index. Strictly gated behind `tor.auto_expand`; harvested
entries persist in the onion store. Domains already covered by the hand-vetted seed are
skipped so we don't duplicate them.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from .models import OnionService
from .registry import load_seed_services
from .store import OnionStore, get_onion_store

logger = logging.getLogger("core.fetch.onion.harvester")

_ANCHORS_PATH = Path(__file__).resolve().parents[2] / "profiles" / "seeds" / "onion_clearnet_anchors.json"


@lru_cache(maxsize=1)
def load_anchor_candidates() -> tuple[str, ...]:
    try:
        raw = json.loads(_ANCHORS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    return tuple(str(a).strip() for a in raw.get("anchors", []) if a)


def _host(url: str) -> str:
    return (urlparse(url).netloc or "").lower().removeprefix("www.")


# Derive a stable service name from a clearnet host ("www.propublica.org" -> "propublica").
def _name_from_anchor(anchor: str) -> str:
    labels = _host(anchor).split(".")
    return labels[-2] if len(labels) >= 2 else (labels[0] if labels else "unknown")


# Fetch one clearnet anchor's Onion-Location over https (no Tor). Returns the URL or None.
def _onion_location(anchor: str, timeout: float) -> str | None:
    from curl_cffi import requests as _r

    try:
        r = _r.get(anchor, impersonate="chrome124", timeout=max(5.0, timeout), allow_redirects=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("harvest fetch failed for %s: %s", anchor, exc)
        return None
    v = r.headers.get("onion-location") or r.headers.get("Onion-Location")
    return v.strip() if v else None


# Scan trusted clearnet anchors and upsert any that self-publish an onion. No-op unless
# tor.auto_expand is enabled. Returns counts for logging/telemetry.
def harvest(*, store: OnionStore | None = None, anchors: tuple[str, ...] | None = None,
            timeout: float = 20.0) -> dict[str, int]:
    from core.config import load_search_config

    if not load_search_config().tor.auto_expand:
        return {"admitted": 0, "skipped": 0, "no_onion": 0, "disabled": 1}

    store = store or get_onion_store()
    anchors = anchors if anchors is not None else load_anchor_candidates()
    seed_hosts = {_host(s.clearnet_anchor) for s in load_seed_services()}

    admitted = skipped = no_onion = 0
    for anchor in anchors:
        if _host(anchor) in seed_hosts:
            skipped += 1  # already hand-vetted in the seed
            continue
        onion = _onion_location(anchor, timeout)
        if not onion or ".onion" not in onion:
            no_onion += 1
            continue
        store.upsert(OnionService(
            name=_name_from_anchor(anchor), category="harvested",
            clearnet_anchor=anchor, onion=onion,
        ))
        admitted += 1
    logger.info("onion harvest: admitted=%d skipped=%d no_onion=%d", admitted, skipped, no_onion)
    return {"admitted": admitted, "skipped": skipped, "no_onion": no_onion, "disabled": 0}
