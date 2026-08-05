# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import reset_task_root  # noqa: E402
from sandbox.api import handle_tool  # noqa: E402


class JobBashRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_task_root()

    def test_jobs_routes_to_registry(self) -> None:
        with patch("sandbox.api.list_background_jobs", return_value={"jobs": [{"job_id": "bg_12345678"}]}):
            result = handle_tool("bash", {"command": "jobs"})

        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["routed"])
        self.assertEqual(json.loads(result["result"]["stdout"])["jobs"][0]["job_id"], "bg_12345678")

    def test_fg_routes_only_background_job_ids(self) -> None:
        with patch("sandbox.api.foreground_background_job", return_value={"job_id": "bg_12345678", "status": "done"}):
            result = handle_tool("bash", {"command": "fg bg_12345678"})

        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["routed"])
        self.assertEqual(json.loads(result["result"]["stdout"])["status"], "done")

    def test_kill_routes_only_background_job_ids(self) -> None:
        with patch("sandbox.api.kill_background_job", return_value={"job_id": "bg_12345678", "status": "killed"}):
            result = handle_tool("bash", {"command": "kill bg_12345678"})

        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["routed"])
        self.assertEqual(json.loads(result["result"]["stdout"])["status"], "killed")

    def test_plain_numeric_kill_falls_back_to_real_bash(self) -> None:
        with patch(
            "sandbox.api.exec_bash",
            return_value={
                "exit_code": 0,
                "stdout": "real kill\n",
                "stderr": "",
                "error": None,
                "elapsed_ms": 1,
                "truncated": False,
                "cwd": ".",
            },
        ) as exec_mock:
            result = handle_tool("bash", {"command": "kill 123"})

        self.assertTrue(result["ok"])
        self.assertFalse(result["result"].get("routed", False))
        self.assertEqual(result["result"]["stdout"], "real kill\n")
        exec_mock.assert_called_once()

    def test_missing_job_returns_routed_error(self) -> None:
        result = handle_tool("bash", {"command": "fg bg_deadbeef"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "job_not_found")
        self.assertTrue(result["result"]["routed"])


if __name__ == "__main__":
    unittest.main()
