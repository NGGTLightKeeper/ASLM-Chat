# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Per-session ephemeral Docker sandbox for deep research overdrive mode.

Each ResearchSession gets its own container that is created on start and
destroyed on stop. Communication is via docker exec + bash — no HTTP, no pipe
protocol, full OS isolation.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from services.deep_research.models import PythonResult

logger = logging.getLogger("services.deep_research.backends.ephemeral_sandbox")

_SANDBOX_IMAGE = "dima1312313/mcp-sandbox:latest"
_WORKSPACE = "/workspace/_sandbox"
_DEFAULT_CPU = "2"
_DEFAULT_MEMORY = "2g"
_DEFAULT_MEMORY_SWAP = "3g"
_DEFAULT_PIDS = "128"


@dataclass
class DownloadResult:
    ok: bool
    path: str = ""
    error: str = ""
    size_bytes: int = 0
    elapsed_ms: int = 0


@dataclass
class EphemeralSandbox:
    """Isolated Docker container scoped to one research session."""

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    image: str = _SANDBOX_IMAGE
    cpu: str = _DEFAULT_CPU
    memory: str = _DEFAULT_MEMORY
    memory_swap: str = _DEFAULT_MEMORY_SWAP
    pids_limit: str = _DEFAULT_PIDS

    _container_name: str = field(init=False, default="")
    _running: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        self._container_name = f"dr-session-{self.session_id}"

    @property
    def container_name(self) -> str:
        return self._container_name

    @property
    def running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Create and start the ephemeral container."""
        cmd = [
            "docker", "run", "-d",
            "--name", self._container_name,
            "--cpus", self.cpu,
            "--memory", self.memory,
            "--memory-swap", self.memory_swap,
            "--pids-limit", self.pids_limit,
            "--no-healthcheck",
            "-e", "SANDBOX_IN_CONTAINER=1",
            self.image,
            "sleep", "infinity",
        ]
        t0 = time.time()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Failed to start sandbox container {self._container_name}: "
                f"{stderr.decode(errors='replace').strip()}"
            )
        self._running = True
        logger.info(
            "Ephemeral sandbox started: container=%s elapsed_ms=%d",
            self._container_name,
            int((time.time() - t0) * 1000),
        )

    async def stop(self) -> None:
        """Destroy the container unconditionally."""
        if not self._running:
            return
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", self._container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=15.0)
        except Exception as exc:
            logger.warning("Failed to remove container %s: %s", self._container_name, exc)
        finally:
            self._running = False
            logger.info("Ephemeral sandbox stopped: container=%s", self._container_name)

    # ------------------------------------------------------------------

    async def exec(self, command: str, timeout_sec: int = 20) -> PythonResult:
        """Run a bash command inside the container and return PythonResult."""
        if not self._running:
            return PythonResult(ok=False, error="Sandbox container is not running.")

        t0 = time.time()
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec",
            "-w", _WORKSPACE,
            self._container_name,
            "bash", "-c", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=float(timeout_sec) + 5.0
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return PythonResult(
                ok=False,
                error=f"Command timed out after {timeout_sec}s",
                elapsed_ms=int((time.time() - t0) * 1000),
            )

        elapsed = int((time.time() - t0) * 1000)
        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        ok = proc.returncode == 0

        return PythonResult(
            ok=ok,
            stdout=stdout,
            stderr=stderr,
            error=None if ok else f"exit code {proc.returncode}",
            elapsed_ms=elapsed,
        )

    async def run_python(self, code: str, timeout_sec: int = 20) -> PythonResult:
        """Execute Python code inside the container."""
        safe = shlex.quote(code)
        return await self.exec(f"python3 -c {safe}", timeout_sec=timeout_sec)

    async def download_file(
        self,
        url: str,
        filename: Optional[str] = None,
        timeout_sec: int = 60,
        max_size_mb: int = 50,
    ) -> DownloadResult:
        """Download a file into the container workspace via curl."""
        if not self._running:
            return DownloadResult(ok=False, error="Sandbox container is not running.")

        if not filename:
            # Derive filename from URL, fallback to random hex
            raw = url.rstrip("/").split("/")[-1].split("?")[0]
            filename = raw if raw and "." in raw else f"download_{uuid.uuid4().hex[:8]}"

        dest = f"{_WORKSPACE}/{filename}"
        max_bytes = max_size_mb * 1024 * 1024

        cmd = (
            f"curl -L --silent --show-error --fail "
            f"--max-filesize {max_bytes} "
            f"--max-time {timeout_sec} "
            f"-o {shlex.quote(dest)} "
            f"{shlex.quote(url)} "
            f"&& stat -c '%s' {shlex.quote(dest)}"
        )

        t0 = time.time()
        result = await self.exec(cmd, timeout_sec=timeout_sec + 5)
        elapsed = int((time.time() - t0) * 1000)

        if not result.ok:
            return DownloadResult(
                ok=False,
                error=result.stderr.strip() or result.error or "curl failed",
                elapsed_ms=elapsed,
            )

        try:
            size_bytes = int(result.stdout.strip().splitlines()[-1])
        except Exception:
            size_bytes = 0

        logger.info(
            "Downloaded %s → %s (%d bytes, %d ms)",
            url, dest, size_bytes, elapsed,
        )
        return DownloadResult(
            ok=True,
            path=dest,
            size_bytes=size_bytes,
            elapsed_ms=elapsed,
        )

    # ------------------------------------------------------------------

    async def __aenter__(self) -> "EphemeralSandbox":
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop()
