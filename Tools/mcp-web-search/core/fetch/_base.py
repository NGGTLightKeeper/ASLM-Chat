# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from dataclasses import dataclass


# Immutable container for a raw HTTP response from any transport backend.
@dataclass(frozen=True, slots=True)
class TransportResponse:
    status: int
    body: bytes
    transport: str = ""

    # Decode the response body as UTF-8 text with replacement for bad bytes.
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")
