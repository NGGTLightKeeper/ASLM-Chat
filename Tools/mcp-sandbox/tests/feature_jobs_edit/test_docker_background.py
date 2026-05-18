# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import reset_task_root  # noqa: E402
import sandbox.docker_host as docker_host_mod  # noqa: E402

TEST_JOB_DIR = "/workspace/.sandbox_jobs/bg_12345678"


class RunResult:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class DockerBackgroundTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_task_root()
        docker_host_mod.JOB_REGISTRY.reset()

    def test_docker_timeout_backgrounds_without_container_restart(self) -> None:
        calls: list[list[str]] = []

        def fake_run(args, timeout=30, **kwargs):
            calls.append(args)
            script = args[-1]
            if "setsid" in script and "job_dir/pid" in script:
                self.assertIn("export job_dir; if command -v setsid", script)
                self.assertIn("setsid bash -lc", script)
                self.assertIn("job_dir/pgid", script)
                self.assertIn("nohup bash -lc", script)
                self.assertNotIn("eval echo", script)
                self.assertIn("home_dollar='$HOME/'", script)
                return RunResult(stdout="9876\n")
            if "/status" in script and "exit_code" in script:
                return RunResult(stdout="running\n\n")
            if "/stdout" in script:
                return RunResult(stdout="partial\n")
            if "/stderr" in script:
                return RunResult(stdout="")
            return RunResult()

        times = iter([100.0, 101.1, 101.2])

        with patch.object(docker_host_mod, "_ensure_container_running", return_value=(True, "ok")), \
             patch.object(docker_host_mod, "_run_command", side_effect=fake_run), \
             patch.object(docker_host_mod, "restart_container") as restart_mock, \
             patch.object(docker_host_mod.time, "time", side_effect=lambda: next(times, 101.2)):
            result = docker_host_mod._exec_bash_docker("pytest", timeout_s=1, background="always")

        self.assertEqual(result["error_type"], "backgrounded")
        self.assertEqual(result["stdout"], "partial\n")
        self.assertRegex(result["job_id"], r"^bg_[0-9a-f]{8}$")
        self.assertTrue(any("setsid bash -lc" in call[-1] for call in calls))
        restart_mock.assert_not_called()

    def test_foreground_docker_job_reads_status_and_output(self) -> None:
        job = docker_host_mod.JOB_REGISTRY.create(
            command="pytest",
            cwd=".",
            runtime="docker",
            pid=9876,
            container_job_dir=TEST_JOB_DIR,
            job_id="bg_12345678",
        )

        def fake_run(args, timeout=30, **kwargs):
            script = args[-1]
            if "/status" in script and "exit_code" in script:
                return RunResult(stdout="done\n0\n")
            if "/stdout" in script:
                return RunResult(stdout="ok\n")
            if "/stderr" in script:
                return RunResult(stdout="")
            return RunResult()

        with patch.object(docker_host_mod, "_run_command", side_effect=fake_run):
            status = docker_host_mod.foreground_background_job(job.job_id)

        self.assertEqual(status["status"], "done")
        self.assertEqual(status["exit_code"], 0)
        self.assertEqual(status["new_stdout"], "ok\n")

    def test_foreground_docker_job_reads_long_single_line_with_bounded_reader(self) -> None:
        job = docker_host_mod.JOB_REGISTRY.create(
            command="python3 -c 'print(\"A\" * 120000)'",
            cwd=".",
            runtime="docker",
            pid=9876,
            container_job_dir=TEST_JOB_DIR,
            job_id="bg_12345678",
        )
        calls: list[str] = []
        marker = (
            "\n\n[output truncated while reading docker job spool: "
            "showed first 30000 bytes and last 30000 bytes of 120000 new bytes]\n\n"
        )

        def fake_run(args, timeout=30, **kwargs):
            script = args[-1]
            calls.append(script)
            if "/status" in script and "exit_code" in script:
                return RunResult(stdout="done\n0\n")
            if "python3 -" in script and "/stdout" in script:
                self.assertNotIn("cat /workspace/.sandbox_jobs/bg_12345678/stdout", script)
                return RunResult(stdout=("A" * 100) + marker + ("B" * 100))
            if "python3 -" in script and "/stderr" in script:
                return RunResult(stdout="")
            if "wc -c" in script:
                return RunResult(stdout="120000\n")
            return RunResult()

        with patch.object(docker_host_mod, "_run_command", side_effect=fake_run):
            status = docker_host_mod.foreground_background_job(job.job_id)

        self.assertTrue(status["truncated"])
        self.assertIn("[output truncated while reading docker job spool:", status["new_stdout"])
        self.assertTrue(any("python3 -" in call and "/stdout" in call for call in calls))

    def test_kill_docker_job_uses_container_pid_file(self) -> None:
        docker_host_mod.JOB_REGISTRY.create(
            command="pytest",
            cwd=".",
            runtime="docker",
            pid=9876,
            container_job_dir=TEST_JOB_DIR,
            job_id="bg_12345678",
        )
        calls: list[list[str]] = []

        def fake_run(args, timeout=30, **kwargs):
            calls.append(args)
            return RunResult()

        with patch.object(docker_host_mod, "_run_command", side_effect=fake_run):
            result = docker_host_mod.kill_background_job("bg_12345678")

        self.assertEqual(result["status"], "killed")
        kill_scripts = [call[-1] for call in calls]
        self.assertTrue(any("pgid=$(cat" in script for script in kill_scripts))
        self.assertTrue(any("kill -TERM -- -\"$pgid\"" in script for script in kill_scripts))
        self.assertTrue(any("kill -KILL -- -\"$pgid\"" in script for script in kill_scripts))

    def test_refresh_marks_stale_running_docker_job_done(self) -> None:
        job = docker_host_mod.JOB_REGISTRY.create(
            command="pytest",
            cwd=".",
            runtime="docker",
            pid=9876,
            container_job_dir=TEST_JOB_DIR,
            job_id="bg_12345678",
        )

        def fake_run(args, timeout=30, **kwargs):
            return RunResult(stdout="running\n\n9876\n9876\nno\n")

        with patch.object(docker_host_mod, "_run_command", side_effect=fake_run):
            refreshed = docker_host_mod._refresh_docker_job(job)

        self.assertEqual(refreshed.status, "done")
        self.assertIsNone(refreshed.exit_code)


if __name__ == "__main__":
    unittest.main()
