from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import reset_task_root  # noqa: E402
import sandbox.container as container_mod  # noqa: E402
import sandbox.exec as exec_mod  # noqa: E402


class BackgroundProcess:
    def __init__(self) -> None:
        self.stdin = io.StringIO()
        self.pid = 4321
        self.returncode = None

    def poll(self):
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


class NativeBackgroundTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_task_root()
        container_mod.JOB_REGISTRY.reset()

    def test_native_timeout_backgrounds_without_killing_process_group(self) -> None:
        fake = BackgroundProcess()
        times = iter([100.0, 101.1, 101.2])

        with patch.object(container_mod.subprocess, "Popen", return_value=fake), \
             patch.object(exec_mod, "_kill_process_group") as killpg_mock, \
             patch.object(container_mod, "restart_container") as restart_mock, \
             patch.object(exec_mod.time, "time", side_effect=lambda: next(times, 101.2)):
            result = container_mod._exec_bash_native("sleep 60", timeout_s=1, background="always")

        self.assertIsNone(result["exit_code"])
        self.assertEqual(result["error_type"], "backgrounded")
        self.assertRegex(result["job_id"], r"^bg_[0-9a-f]{8}$")
        killpg_mock.assert_not_called()
        restart_mock.assert_not_called()

    def test_foreground_native_job_finalizes_exit_code(self) -> None:
        fake = BackgroundProcess()
        times = iter([100.0, 101.1, 101.2])

        with patch.object(container_mod.subprocess, "Popen", return_value=fake), \
             patch.object(exec_mod.time, "time", side_effect=lambda: next(times, 101.2)):
            result = container_mod._exec_bash_native("pytest", timeout_s=1, background="always")

        job = container_mod.JOB_REGISTRY.get(result["job_id"])
        (job.host_job_dir / "stdout").write_text("done\n", encoding="utf-8")
        fake.returncode = 0

        status = container_mod.foreground_background_job(job.job_id)

        self.assertEqual(status["status"], "done")
        self.assertEqual(status["exit_code"], 0)
        self.assertEqual(status["new_stdout"], "done\n")


if __name__ == "__main__":
    unittest.main()
