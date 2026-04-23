# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sandbox.responses import SandboxToolError


JOB_ID_PREFIX = "bg_"


@dataclass
class BackgroundJob:
    job_id: str
    command: str
    cwd: str
    runtime: str
    started_at: float
    pid: int | None = None
    process: Any | None = None
    host_job_dir: Path | None = None
    container_job_dir: str | None = None
    status: str = "running"
    exit_code: int | None = None
    stdout_offset: int = 0
    stderr_offset: int = 0

    def to_result(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "command": self.command,
            "cwd": self.cwd,
            "runtime": self.runtime,
            "pid": self.pid,
            "status": self.status,
            "exit_code": self.exit_code,
            "elapsed_s": round(time.time() - self.started_at, 3),
            "host_job_dir": str(self.host_job_dir) if self.host_job_dir else None,
            "container_job_dir": self.container_job_dir,
        }


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, BackgroundJob] = {}
        self._lock = threading.Lock()

    def create(
        self,
        *,
        command: str,
        cwd: str,
        runtime: str,
        pid: int | None = None,
        host_job_dir: Path | str | None = None,
        container_job_dir: str | None = None,
        process: Any | None = None,
        job_id: str | None = None,
    ) -> BackgroundJob:
        if runtime not in {"native", "docker"}:
            raise ValueError("runtime must be 'native' or 'docker'.")

        normalized_id = job_id or self._new_job_id()
        job = BackgroundJob(
            job_id=normalized_id,
            command=command,
            cwd=cwd,
            runtime=runtime,
            started_at=time.time(),
            pid=pid,
            process=process,
            host_job_dir=Path(host_job_dir) if host_job_dir is not None else None,
            container_job_dir=container_job_dir,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> BackgroundJob:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise SandboxToolError("job_not_found", f"Background job not found: {job_id}")
        return job

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
        return [job.to_result() for job in jobs]

    def read_output(self, job_id: str, stream: str = "stdout", *, incremental: bool = True) -> str:
        if stream not in {"stdout", "stderr"}:
            raise ValueError("stream must be 'stdout' or 'stderr'.")

        job = self.get(job_id)
        if job.host_job_dir is None:
            raise SandboxToolError(
                "job_output_unavailable",
                f"Job output is not available on host filesystem: {job_id}",
            )

        output_path = job.host_job_dir / stream
        if not output_path.exists():
            return ""

        content = output_path.read_text(encoding="utf-8", errors="replace")
        if not incremental:
            return content

        offset_attr = f"{stream}_offset"
        offset = int(getattr(job, offset_attr))
        new_content = content[offset:]
        setattr(job, offset_attr, len(content))
        return new_content

    def mark_done(self, job_id: str, exit_code: int | None) -> BackgroundJob:
        job = self.get(job_id)
        job.status = "done"
        job.exit_code = exit_code
        return job

    def mark_killed(self, job_id: str) -> BackgroundJob:
        job = self.get(job_id)
        job.status = "killed"
        if job.exit_code is None:
            job.exit_code = -9
        return job

    def purge_stale(self, ttl_seconds: float = 3600.0) -> int:
        """Remove finished jobs older than ttl_seconds. Returns count removed."""
        import shutil
        cutoff = time.time() - ttl_seconds
        with self._lock:
            stale_ids = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in ("done", "killed") and job.started_at < cutoff
            ]
            removed = [self._jobs.pop(job_id) for job_id in stale_ids]
        for job in removed:
            if job.host_job_dir and job.host_job_dir.exists():
                shutil.rmtree(job.host_job_dir, ignore_errors=True)
        return len(removed)

    def reset(self) -> None:
        with self._lock:
            self._jobs.clear()

    def _new_job_id(self) -> str:
        self.purge_stale()
        while True:
            candidate = f"{JOB_ID_PREFIX}{uuid.uuid4().hex[:8]}"
            with self._lock:
                if candidate not in self._jobs:
                    return candidate


JOB_REGISTRY = JobRegistry()
