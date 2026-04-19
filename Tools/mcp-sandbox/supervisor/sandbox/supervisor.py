from __future__ import annotations

import os
import sys
from pathlib import Path


os.environ.setdefault("SANDBOX_IN_CONTAINER", "1")
os.environ.setdefault("SANDBOX_HOST_WORKSPACE", "/workspace")
os.environ.setdefault("SANDBOX_SUPERVISOR_SRC", "/opt/sandbox-src")
os.environ.setdefault("SANDBOX_SUPERVISOR_VENV", "/opt/sandbox-venv")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")


def _prefer_supervisor_source() -> None:
    """Prefer the read-only source bind when the image also has a copy."""

    supervisor_src = Path(os.environ["SANDBOX_SUPERVISOR_SRC"])
    if supervisor_src.is_dir() and str(supervisor_src) not in sys.path:
        sys.path.insert(0, str(supervisor_src))


def _protect_from_oom() -> None:
    """Best-effort supervisor OOM protection."""

    try:
        Path("/proc/self/oom_score_adj").write_text("-1000\n", encoding="utf-8")
    except OSError:
        pass


def _set_process_title() -> None:
    """Use a stable process title when setproctitle is available."""

    try:
        from setproctitle import setproctitle
    except Exception:
        return

    try:
        setproctitle("mcp-supervisor")
    except Exception:
        pass


def _cleanup_orphaned_job_dirs() -> None:
    """Remove .sandbox_jobs dirs left from previous supervisor sessions."""
    import shutil
    from sandbox.workspace import task_root
    jobs_root = task_root() / ".sandbox_jobs"
    if not jobs_root.exists():
        return
    for entry in jobs_root.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)


def main() -> None:
    _prefer_supervisor_source()
    _protect_from_oom()
    _set_process_title()
    _cleanup_orphaned_job_dirs()

    from mcp.server.fastmcp import FastMCP
    from sandbox.tools import register_tools

    if "--healthcheck" in sys.argv[1:]:
        mcp = FastMCP("SandboxHealthcheck")
        register_tools(mcp)
        print("sandbox-supervisor-pong-v2", flush=True)
        return

    mcp = FastMCP("Sandbox")
    register_tools(mcp)
    mcp.run()


if __name__ == "__main__":
    main()
