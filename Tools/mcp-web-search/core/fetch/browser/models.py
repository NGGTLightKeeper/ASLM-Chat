# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Shared data shapes for the warm-browser layer.

BrowserFetch is the single outcome type every caller depends on. Mirrors the
daemon's wire payload (scripts/browser_daemon.py ScrapeResult) so the HTTP client
can build one from a JSON body verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass

# Terminal fetch statuses. Mirrors the daemon contract; "unavailable" is added for
# the client side (daemon unreachable / browser disabled) so callers can tell a
# real block apart from "we never asked the browser".
STATUS_OK = "ok"
STATUS_BLOCKED = "blocked"
STATUS_TIMEOUT = "timeout"
STATUS_ERROR = "error"
STATUS_UNAVAILABLE = "unavailable"


# Outcome of one page fetch through the warm browser daemon.
@dataclass(slots=True)
class BrowserFetch:
    url: str
    status: str = STATUS_ERROR
    html: str = ""
    text: str = ""
    title: str = ""
    engine: str = ""          # chromium (warm daemon)
    backend: str = "warm"
    ms: float = 0.0
    error: str = ""

    # True only for a genuinely successful scrape with usable HTML.
    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK and bool(self.html)

    # True when the browser confirmed an anti-bot wall (distinct from never-asked).
    @property
    def blocked(self) -> bool:
        return self.status == STATUS_BLOCKED

    # Build a BrowserFetch from the daemon's JSON /fetch response body.
    @classmethod
    def from_daemon(cls, body: dict, *, backend: str = "warm") -> "BrowserFetch":
        return cls(
            url=str(body.get("url") or ""),
            status=str(body.get("status") or STATUS_ERROR),
            html=str(body.get("html") or ""),
            text=str(body.get("text") or ""),
            title=str(body.get("title") or ""),
            engine=str(body.get("engine") or ""),
            backend=backend,
            ms=float(body.get("ms") or 0.0),
            error=str(body.get("error") or ""),
        )
