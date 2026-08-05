# Copyright NEXTGGTECH. Elastic License 2.0.

"""Loader for the academic domain registry seed (`profiles/seeds/academic_registry.json`).

The seed is the source of truth for *which* scholarly aggregators exist and *how* to
reach each (method = json_api / http / browser, rps/burst pacing, the open REST endpoint
in `json_api_hint`, and field notes). The engine builds its provider set from the
`json_api` entries — open, keyless REST APIs that return rich structured JSON without
scraping. `http`/`browser` tiers (arxiv html, pubmed, semanticscholar) are described here
but reached through their own clients or deferred to the browser path.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

_SEED_PATH = Path(__file__).resolve().parents[2] / "profiles" / "seeds" / "academic_registry.json"


# One registry row: a scholarly domain plus how to reach it.
@dataclass(frozen=True, slots=True)
class AcademicDomain:
    pattern: str
    tier: str                 # friendly / moderate / hardened
    method: str               # json_api / http / browser
    rps: float
    burst: int
    json_api_hint: str
    text_search_capable: bool
    aliases: tuple[str, ...]
    notes: str

    # The registrable host the records of this domain live under (used as source_domain).
    @property
    def host(self) -> str:
        return self.pattern


def _coerce(entry: dict[str, Any]) -> AcademicDomain:
    return AcademicDomain(
        pattern=str(entry.get("pattern") or "").strip().lower(),
        tier=str(entry.get("tier") or "moderate").strip().lower(),
        method=str(entry.get("method") or "http").strip().lower(),
        rps=float(entry.get("rps") or 1.0),
        burst=int(entry.get("burst") or 1),
        json_api_hint=str(entry.get("json_api_hint") or "").strip(),
        text_search_capable=bool(entry.get("text_search_capable", True)),
        aliases=tuple(str(a).strip().lower() for a in entry.get("aliases", []) if a),
        notes=str(entry.get("notes") or "").strip(),
    )


@lru_cache(maxsize=1)
def load_registry() -> tuple[AcademicDomain, ...]:
    try:
        raw = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    return tuple(_coerce(e) for e in raw.get("domains", []) if isinstance(e, dict) and e.get("pattern"))


# Registry rows reachable by a keyless REST endpoint and usable for free-text search.
def json_api_domains() -> tuple[AcademicDomain, ...]:
    return tuple(
        d for d in load_registry()
        if d.method == "json_api" and d.json_api_hint and d.text_search_capable
    )


# Look up a registry row by host (or alias), walking nothing — exact match on pattern/alias.
def domain_for(host: str) -> AcademicDomain | None:
    h = (host or "").strip().lower().removeprefix("www.")
    for d in load_registry():
        if h == d.pattern or h in d.aliases:
            return d
    return None
