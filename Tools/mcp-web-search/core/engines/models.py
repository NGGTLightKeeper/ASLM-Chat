# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


# Possible outcomes of one engine parse attempt.
class ParseStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    EMPTY = "empty"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"
    CHANGED = "changed"
    ERROR = "error"


# Immutable representation of a single search result.
@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""


# Immutable HTTP request descriptor passed to transport backends.
@dataclass(frozen=True, slots=True)
class EngineRequest:
    method: str
    url: str
    params: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    primp_target: str = "chrome_131"
    primp_os: str = "windows"
    # The engine that owns this request's identity (e.g. "startpage"). Keys the persistent
    # HTTP cookie history (Stage B) so each engine replays and accumulates its own cookies.
    identity_key: str = ""


# Mutable result container produced by each engine parser.
@dataclass(slots=True)
class EngineParseResult:
    engine: str
    status: ParseStatus
    results: list[SearchResult] = field(default_factory=list)
    parser_variant: str = ""
    cards_seen: int = 0
    malformed_cards: int = 0
    diagnostics: list[str] = field(default_factory=list)

    # Return the fraction of seen cards that produced usable results.
    @property
    def coverage(self) -> float:
        if self.cards_seen <= 0:
            return 1.0 if self.results else 0.0
        return min(1.0, len(self.results) / self.cards_seen)
