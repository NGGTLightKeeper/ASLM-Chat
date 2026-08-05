# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import os
import sys
from pathlib import Path


os.environ.setdefault("SANDBOX_IN_CONTAINER", "1")
os.environ.setdefault("SANDBOX_HOST_WORKSPACE", "/workspace")
os.environ.setdefault("SANDBOX_SUPERVISOR_SRC", "/opt/sandbox-src")
os.environ.setdefault("SANDBOX_SUPERVISOR_VENV", "/opt/sandbox-venv")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")


# Prefer the read-only source bind when the image also has a copy.
def _prefer_supervisor_source() -> None:
    supervisor_src = Path(os.environ["SANDBOX_SUPERVISOR_SRC"])
    if supervisor_src.is_dir() and str(supervisor_src) not in sys.path:
        sys.path.insert(0, str(supervisor_src))


# Best-effort supervisor OOM protection.
def _protect_from_oom() -> None:
    try:
        Path("/proc/self/oom_score_adj").write_text("-1000\n", encoding="utf-8")
    except OSError:
        pass


# Use a stable process title when setproctitle is available.
def _set_process_title() -> None:
    try:
        from setproctitle import setproctitle
    except Exception:
        return

    try:
        setproctitle("mcp-supervisor")
    except Exception:
        pass


# Kill and remove job dirs left from previous supervisor sessions.
def _cleanup_orphaned_job_dirs() -> None:
    import os
    import signal
    import shutil

    from sandbox.exec import job_root

    jobs_root = job_root()
    if jobs_root.is_symlink():
        jobs_root.unlink(missing_ok=True)
        jobs_root.mkdir(parents=True, exist_ok=True)
        return
    if not jobs_root.exists():
        return
    for entry in jobs_root.iterdir():
        if entry.is_symlink():
            entry.unlink(missing_ok=True)
            continue
        if not entry.is_dir():
            continue
        pgid_path = entry / "pgid"
        pid_path = entry / "pid"
        for path in (pgid_path, pid_path):
            try:
                target_id = int(path.read_text(encoding="utf-8").strip())
            except Exception:
                continue
            try:
                if path.name == "pgid":
                    os.killpg(target_id, signal.SIGTERM)
                else:
                    os.kill(target_id, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception:
                pass
        for path in (pgid_path, pid_path):
            try:
                target_id = int(path.read_text(encoding="utf-8").strip())
            except Exception:
                continue
            try:
                if path.name == "pgid":
                    os.killpg(target_id, signal.SIGKILL)
                else:
                    os.kill(target_id, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except Exception:
                pass
        shutil.rmtree(entry, ignore_errors=True)


# Start FastMCP with sandbox tools (or healthcheck when requested).
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
