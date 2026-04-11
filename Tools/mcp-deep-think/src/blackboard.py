# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""SharedBlackboard for structured inter-agent signal exchange.

Agents publish short, typed signals (findings, contradictions,
confidence updates) which other agents can read at the start of
each subsequent iteration.  No free-form chat.
"""

from __future__ import annotations

import asyncio
import time
from typing import List

from pydantic import BaseModel, Field


# Signal types that agents can publish.
SIGNAL_TYPES = ("finding", "contradiction", "confidence_update", "question")


class Signal(BaseModel):
    """One structured message published by an agent."""

    agent_id: str
    iteration: int
    signal_type: str  # one of SIGNAL_TYPES
    content: str
    confidence: float = 0.5
    references: list[str] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)


class SharedBlackboard:
    """Thread-safe shared store for inter-agent signals."""

    def __init__(
        self,
        max_signals_per_read: int = 20,
        signal_max_chars: int = 300,
    ):
        self._signals: list[Signal] = []
        self._lock = asyncio.Lock()
        self.max_signals_per_read = max_signals_per_read
        self.signal_max_chars = signal_max_chars

    async def publish(self, signal: Signal) -> None:
        """Append a signal to the shared board."""
        # Truncate content to configured maximum.
        if len(signal.content) > self.signal_max_chars:
            signal = signal.model_copy(
                update={"content": signal.content[: self.signal_max_chars] + "..."}
            )
        async with self._lock:
            self._signals.append(signal)

    async def read_since(
        self,
        agent_id: str,
        after_timestamp: float = 0.0,
    ) -> List[Signal]:
        """Return signals from *other* agents published after *after_timestamp*.

        At most *max_signals_per_read* signals are returned (most recent first).
        """
        async with self._lock:
            relevant = [
                s
                for s in self._signals
                if s.agent_id != agent_id and s.timestamp > after_timestamp
            ]
        # Return most recent first, capped.
        relevant.sort(key=lambda s: s.timestamp, reverse=True)
        return relevant[: self.max_signals_per_read]

    async def read_all(self) -> List[Signal]:
        """Return a snapshot of every signal on the board."""
        async with self._lock:
            return list(self._signals)

    def summary_for_prompt(
        self,
        signals: List[Signal],
        max_chars: int = 2000,
    ) -> str:
        """Format signals into a compact text block for prompt injection."""
        if not signals:
            return ""

        lines: list[str] = []
        total = 0
        for sig in signals:
            line = f"[{sig.agent_id} iter={sig.iteration} {sig.signal_type}] {sig.content}"
            if sig.references:
                line += f" (refs: {', '.join(sig.references[:3])})"
            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line) + 1  # +1 for newline
        return "\n".join(lines)
