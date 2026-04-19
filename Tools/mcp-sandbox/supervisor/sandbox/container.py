"""Container-side facade — native execution only (no Docker path)."""
from __future__ import annotations

from sandbox.exec import (
    _exec_bash_native as exec_bash,  # noqa: F401
    _job_files_result,
    _kill_process_group,
)
from sandbox.jobs import JOB_REGISTRY


def list_background_jobs() -> dict:
    return {"jobs": JOB_REGISTRY.list_jobs()}


def foreground_background_job(job_id: str) -> dict:
    job = JOB_REGISTRY.get(job_id)
    process = job.process
    if process is not None and job.status == "running":
        returncode = process.poll()
        if returncode is not None:
            JOB_REGISTRY.mark_done(job.job_id, returncode)
    stdout, stderr, truncated = _job_files_result(job, incremental=True)
    return {
        **job.to_result(),
        "new_stdout": stdout,
        "new_stderr": stderr,
        "truncated": truncated,
    }


def kill_background_job(job_id: str) -> dict:
    job = JOB_REGISTRY.get(job_id)
    process = job.process
    if process is not None and process.poll() is None:
        _kill_process_group(process)
    JOB_REGISTRY.mark_killed(job.job_id)
    return job.to_result()
