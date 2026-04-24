# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import reset_task_root  # noqa: E402
from sandbox.jobs import JobRegistry  # noqa: E402


class JobRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task_root = reset_task_root()
        self.job_dir = self.task_root / "job"
        self.job_dir.mkdir()
        (self.job_dir / "stdout").write_text("alpha\n", encoding="utf-8")
        (self.job_dir / "stderr").write_text("", encoding="utf-8")

    def test_create_and_list_job(self) -> None:
        registry = JobRegistry()

        job = registry.create(
            command="sleep 10",
            cwd=".",
            runtime="native",
            pid=123,
            host_job_dir=self.job_dir,
        )

        self.assertRegex(job.job_id, r"^bg_[0-9a-f]{8}$")
        listing = registry.list_jobs()
        self.assertEqual(listing[0]["job_id"], job.job_id)
        self.assertEqual(listing[0]["status"], "running")
        self.assertEqual(listing[0]["pid"], 123)

    def test_reads_output_incrementally(self) -> None:
        registry = JobRegistry()
        job = registry.create(
            command="pytest",
            cwd=".",
            runtime="native",
            pid=123,
            host_job_dir=self.job_dir,
        )

        first = registry.read_output(job.job_id, "stdout", incremental=True)
        (self.job_dir / "stdout").write_text("alpha\nbeta\n", encoding="utf-8")
        second = registry.read_output(job.job_id, "stdout", incremental=True)
        full = registry.read_output(job.job_id, "stdout", incremental=False)

        self.assertEqual(first, "alpha\n")
        self.assertEqual(second, "beta\n")
        self.assertEqual(full, "alpha\nbeta\n")

    def test_state_transitions(self) -> None:
        registry = JobRegistry()
        job = registry.create(
            command="pytest",
            cwd=".",
            runtime="native",
            pid=123,
            host_job_dir=self.job_dir,
        )

        registry.mark_done(job.job_id, exit_code=0)
        self.assertEqual(registry.get(job.job_id).status, "done")
        self.assertEqual(registry.get(job.job_id).exit_code, 0)

        registry.mark_killed(job.job_id)
        self.assertEqual(registry.get(job.job_id).status, "killed")


if __name__ == "__main__":
    unittest.main()
