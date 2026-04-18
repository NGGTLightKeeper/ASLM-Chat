# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Research Workspace — session registry for agentic deep research.

Provides isolated, background-capable research sessions with status tracking.
Each session runs in its own asyncio.Task so it never blocks the MCP event loop.

Public API
----------
ResearchWorkspace   -- singleton session registry
get_workspace()     -- module-level accessor to the shared instance

Usage
-----
    workspace = get_workspace()

    # Start a background research session
    session_id = await workspace.start(question="What is...", depth="standard")

    # Poll status (non-blocking)
    status = workspace.status(session_id)
    # {"id": "...", "state": "running"|"done"|"error", "elapsed_sec": 12.4,
    #  "report": "...", "error": None}

    # Block until done (optional)
    report = await workspace.wait(session_id)

    # List all active sessions
    active = workspace.list_sessions()
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("core.sandbox.research_workspace")

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

@dataclass
class _WorkspaceSession:
    id: str
    question: str
    depth: str
    state: str  # "running" | "done" | "error"
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    report: str = ""
    error: Optional[str] = None
    task: Optional[asyncio.Task] = field(default=None, repr=False)

    @property
    def elapsed_sec(self) -> float:
        end = self.finished_at or time.time()
        return round(end - self.started_at, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "depth": self.depth,
            "state": self.state,
            "elapsed_sec": self.elapsed_sec,
            "report": self.report,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

class ResearchWorkspace:
    """Singleton registry that manages isolated deep research sessions.

    Each session is a separate asyncio.Task — it runs concurrently with the
    MCP server event loop without blocking it. Results are stored in-memory
    keyed by session_id and are available via :meth:`status` or :meth:`wait`.
    """

    def __init__(self, max_concurrent: int = 3):
        self._sessions: dict[str, _WorkspaceSession] = {}
        self._sem = asyncio.Semaphore(max_concurrent)

    # -- Public API ----------------------------------------------------------

    async def start(
        self,
        question: str,
        depth: str = "standard",
        hard_timeout: Optional[float] = None,
    ) -> str:
        """Enqueue a research session and return its session_id immediately."""
        session_id = secrets.token_hex(6)
        ws_session = _WorkspaceSession(
            id=session_id,
            question=question,
            depth=depth,
            state="running",
        )
        self._sessions[session_id] = ws_session

        task = asyncio.create_task(
            self._run_session(ws_session, hard_timeout),
            name=f"research:{session_id}",
        )
        ws_session.task = task

        logger.info(
            "workspace.start session_id=%s question=%r depth=%s",
            session_id, question[:80], depth,
        )
        return session_id

    def status(self, session_id: str) -> dict[str, Any]:
        """Return current status dict for a session (non-blocking)."""
        session = self._sessions.get(session_id)
        if session is None:
            return {"id": session_id, "state": "not_found", "error": "Session ID not found."}
        return session.to_dict()

    async def wait(self, session_id: str, timeout: Optional[float] = None) -> str:
        """Block until the session finishes and return the report.

        Raises TimeoutError if *timeout* seconds elapse without completion.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Session {session_id!r} not found.")
        if session.task is not None and not session.task.done():
            try:
                await asyncio.wait_for(asyncio.shield(session.task), timeout=timeout)
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Session {session_id} did not finish within {timeout}s."
                ) from None
        if session.error:
            raise RuntimeError(session.error)
        return session.report

    def cancel(self, session_id: str) -> bool:
        """Cancel a running session. Returns True if cancellation was issued."""
        session = self._sessions.get(session_id)
        if session is None or session.task is None or session.task.done():
            return False
        session.task.cancel()
        session.state = "error"
        session.error = "Cancelled by caller."
        session.finished_at = time.time()
        logger.info("workspace.cancel session_id=%s", session_id)
        return True

    def list_sessions(self) -> list[dict[str, Any]]:
        """Return status dicts for all sessions (completed and running)."""
        return [s.to_dict() for s in self._sessions.values()]

    def purge_completed(self, max_age_sec: float = 3600.0) -> int:
        """Remove completed sessions older than *max_age_sec*. Returns count."""
        now = time.time()
        to_remove = [
            sid for sid, s in self._sessions.items()
            if s.state in ("done", "error")
            and s.finished_at is not None
            and now - s.finished_at > max_age_sec
        ]
        for sid in to_remove:
            del self._sessions[sid]
        if to_remove:
            logger.info("workspace.purge removed=%d", len(to_remove))
        return len(to_remove)

    # -- Internal ------------------------------------------------------------

    async def _run_session(
        self,
        session: _WorkspaceSession,
        hard_timeout: Optional[float],
    ) -> None:
        """Execute research in isolation and store result in the session."""
        from services.deep_research.orchestrator import run_deep_research

        async with self._sem:
            try:
                logger.info(
                    "workspace.run_start session_id=%s question=%r",
                    session.id, session.question[:80],
                )
                report = await run_deep_research(
                    question=session.question,
                    depth=session.depth,
                    hard_timeout=hard_timeout,
                )
                session.report = report
                session.state = "done"
                logger.info(
                    "workspace.run_done session_id=%s elapsed=%.1fs chars=%d",
                    session.id, session.elapsed_sec, len(report),
                )
            except asyncio.CancelledError:
                session.state = "error"
                session.error = "Session was cancelled."
                logger.info("workspace.run_cancelled session_id=%s", session.id)
                raise
            except Exception as exc:
                session.state = "error"
                session.error = f"{type(exc).__name__}: {exc}"
                logger.error(
                    "workspace.run_error session_id=%s error=%s",
                    session.id, session.error,
                )
            finally:
                session.finished_at = time.time()


# ---------------------------------------------------------------------------
# Module-level singleton accessor
# ---------------------------------------------------------------------------

_workspace: Optional[ResearchWorkspace] = None


def get_workspace() -> ResearchWorkspace:
    """Return (or lazily create) the shared workspace singleton."""
    global _workspace
    if _workspace is None:
        _workspace = ResearchWorkspace()
    return _workspace
