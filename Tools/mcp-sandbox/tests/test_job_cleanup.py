# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Tests for background job dir lifecycle and cleanup behavior.

Covers:
- should_use_background threshold logic
- Sync-completed job dirs are removed immediately
- Truly backgrounded (timed-out) job dirs are kept for polling
- purge_stale cleans both registry and filesystem
- Startup orphan cleanup removes dirs from previous sessions
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp"
if str(TMP) not in sys.path:
    sys.path.insert(0, str(TMP))

WORKSPACE = ROOT / ".test_workspace_jobs"
os.environ["SANDBOX_HOST_WORKSPACE"] = str(WORKSPACE)
os.environ["SANDBOX_IN_CONTAINER"] = "1"
os.environ["SANDBOX_COMMAND_USER"] = ""
os.environ["SANDBOX_JOB_ROOT"] = str(WORKSPACE / ".sandbox_jobs")

from sandbox.config import BACKGROUND_TIMEOUT_THRESHOLD  # noqa: E402
from sandbox.exec import should_use_background, _exec_bash_native_background, job_root  # noqa: E402
from sandbox.jobs import JOB_REGISTRY  # noqa: E402
from sandbox.workspace import task_root  # noqa: E402
from sandbox.supervisor import _cleanup_orphaned_job_dirs  # noqa: E402


def _jobs_root() -> Path:
    return job_root()


def _native_bash_available() -> bool:
    try:
        result = subprocess.run(["bash", "-lc", "true"], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


class TestShouldUseBackground(unittest.TestCase):
    """should_use_background routing logic."""

    def test_never_mode_always_false(self):
        self.assertFalse(should_use_background("sleep 100", 600, "never"))

    def test_always_mode_always_true(self):
        self.assertTrue(should_use_background("echo hi", 1, "always"))

    def test_auto_high_timeout_triggers_background(self):
        self.assertTrue(
            should_use_background("echo hi", BACKGROUND_TIMEOUT_THRESHOLD, "auto")
        )

    def test_auto_low_timeout_no_background(self):
        self.assertFalse(
            should_use_background("echo hi", BACKGROUND_TIMEOUT_THRESHOLD - 1, "auto")
        )

    def test_auto_long_running_pattern_triggers_background(self):
        self.assertTrue(should_use_background("pip install numpy", 1, "auto"))
        self.assertTrue(should_use_background("apt-get update", 1, "auto"))
        self.assertTrue(should_use_background("pytest tests/", 1, "auto"))

    def test_auto_plain_command_low_timeout_no_background(self):
        self.assertFalse(should_use_background("python script.py", 5, "auto"))


@unittest.skipIf(not _native_bash_available(), "native bash is not available in this test environment")
class TestJobDirCleanupOnSyncCompletion(unittest.TestCase):
    """Job dirs for synchronously completed commands must be deleted."""

    def setUp(self):
        JOB_REGISTRY.reset()
        shutil.rmtree(WORKSPACE, ignore_errors=True)
        shutil.rmtree(_jobs_root(), ignore_errors=True)
        task_root().mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        JOB_REGISTRY.reset()
        shutil.rmtree(WORKSPACE, ignore_errors=True)

    def test_quick_command_no_leftover_dir(self):
        """A command that finishes quickly leaves no .sandbox_jobs entry."""
        result = _exec_bash_native_background("echo hello", timeout_s=10)
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("hello", result["stdout"])
        self.assertFalse(_jobs_root().exists() and any(_jobs_root().iterdir()),
                         ".sandbox_jobs should be empty after sync completion")

    def test_job_not_in_registry_after_dir_cleanup(self):
        """After sync completion no live job directory is retained."""
        result = _exec_bash_native_background("echo hi", timeout_s=10)
        self.assertEqual(result["exit_code"], 0)
        job_id = result.get("job_id")
        if job_id:
            job = JOB_REGISTRY.get(job_id)
            self.assertEqual(job.status, "done")
            if job.host_job_dir:
                self.assertFalse(job.host_job_dir.exists(),
                                 "job dir must be deleted after sync completion")
        else:
            self.assertFalse(JOB_REGISTRY.list_jobs())

    def test_multiple_quick_commands_no_accumulation(self):
        """Repeated quick commands don't accumulate dirs."""
        for i in range(5):
            _exec_bash_native_background(f"echo cmd{i}", timeout_s=10)
        dirs = list(_jobs_root().iterdir()) if _jobs_root().exists() else []
        self.assertEqual(len(dirs), 0, f"Expected 0 dirs, found {len(dirs)}: {dirs}")

    def test_failed_command_dir_also_cleaned(self):
        """Non-zero exit codes also clean up the dir."""
        result = _exec_bash_native_background("exit 1", timeout_s=10)
        self.assertEqual(result["exit_code"], 1)
        dirs = list(_jobs_root().iterdir()) if _jobs_root().exists() else []
        self.assertEqual(len(dirs), 0, "Dir should be gone even after non-zero exit")


@unittest.skipIf(not _native_bash_available(), "native bash is not available in this test environment")
class TestJobDirKeptForTrulyBackgrounded(unittest.TestCase):
    """Commands that time out must keep their dir for incremental polling."""

    def setUp(self):
        JOB_REGISTRY.reset()
        shutil.rmtree(WORKSPACE, ignore_errors=True)
        shutil.rmtree(_jobs_root(), ignore_errors=True)
        task_root().mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        JOB_REGISTRY.reset()
        shutil.rmtree(WORKSPACE, ignore_errors=True)

    def test_timed_out_job_keeps_dir(self):
        """A command that exceeds timeout_s returns error_type=backgrounded and keeps dir."""
        result = _exec_bash_native_background("sleep 30", timeout_s=1)
        self.assertIsNone(result["exit_code"])
        self.assertEqual(result.get("error_type"), "backgrounded")
        job_id = result.get("job_id")
        self.assertIsNotNone(job_id)
        job = JOB_REGISTRY.get(job_id)
        self.assertIsNotNone(job.host_job_dir)
        self.assertTrue(job.host_job_dir.exists(),
                        "Dir must be kept for a truly backgrounded job")
        # Cleanup the lingering process
        if job.process:
            try:
                import signal
                os.killpg(job.process.pid, signal.SIGKILL)
            except Exception:
                job.process.kill()


class TestPurgeStaleFilesystemCleanup(unittest.TestCase):
    """purge_stale must remove both registry entries and filesystem dirs."""

    def setUp(self):
        JOB_REGISTRY.reset()
        shutil.rmtree(WORKSPACE, ignore_errors=True)
        shutil.rmtree(_jobs_root(), ignore_errors=True)
        task_root().mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        JOB_REGISTRY.reset()
        shutil.rmtree(WORKSPACE, ignore_errors=True)

    def test_purge_stale_removes_done_dirs(self):
        """purge_stale with ttl=0 removes all done/killed jobs and their dirs."""
        # Create a fake done job with a real dir
        from sandbox.jobs import BackgroundJob
        job_dir = _jobs_root() / "bg_test001"
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "stdout").write_text("out", encoding="utf-8")

        job = JOB_REGISTRY.create(
            command="echo test",
            cwd=".",
            runtime="native",
            host_job_dir=job_dir,
            job_id="bg_test001",
        )
        JOB_REGISTRY.mark_done(job.job_id, 0)
        # Force the job to appear stale by backdating started_at
        job.started_at = time.time() - 7200

        removed = JOB_REGISTRY.purge_stale(ttl_seconds=3600)
        self.assertEqual(removed, 1)
        self.assertFalse(job_dir.exists(), "purge_stale must delete the dir from disk")

    def test_purge_stale_keeps_running_jobs(self):
        """purge_stale must not touch still-running jobs."""
        job_dir = _jobs_root() / "bg_test002"
        job_dir.mkdir(parents=True, exist_ok=True)
        JOB_REGISTRY.create(
            command="sleep 999",
            cwd=".",
            runtime="native",
            host_job_dir=job_dir,
            job_id="bg_test002",
        )
        removed = JOB_REGISTRY.purge_stale(ttl_seconds=0)
        self.assertEqual(removed, 0)
        self.assertTrue(job_dir.exists(), "Running job dir must not be removed")


class TestStartupOrphanCleanup(unittest.TestCase):
    """_cleanup_orphaned_job_dirs removes all dirs on supervisor startup."""

    def setUp(self):
        JOB_REGISTRY.reset()
        shutil.rmtree(WORKSPACE, ignore_errors=True)
        shutil.rmtree(_jobs_root(), ignore_errors=True)
        task_root().mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        JOB_REGISTRY.reset()
        shutil.rmtree(WORKSPACE, ignore_errors=True)

    def test_cleans_all_dirs_on_startup(self):
        """Orphaned dirs from previous sessions are removed."""
        for i in range(3):
            d = _jobs_root() / f"bg_orphan{i:03d}"
            d.mkdir(parents=True, exist_ok=True)
            (d / "stdout").write_text("stale output", encoding="utf-8")

        self.assertEqual(len(list(_jobs_root().iterdir())), 3)
        _cleanup_orphaned_job_dirs()
        remaining = list(_jobs_root().iterdir()) if _jobs_root().exists() else []
        self.assertEqual(len(remaining), 0, f"All orphans must be gone, found: {remaining}")

    def test_noop_when_no_jobs_dir(self):
        """No error if .sandbox_jobs doesn't exist yet."""
        jobs_root = _jobs_root()
        if jobs_root.exists():
            shutil.rmtree(jobs_root)
        _cleanup_orphaned_job_dirs()  # must not raise


if __name__ == "__main__":
    unittest.main(verbosity=2)
