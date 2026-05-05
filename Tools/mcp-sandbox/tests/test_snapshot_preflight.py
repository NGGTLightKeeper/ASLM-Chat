# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ.setdefault("SANDBOX_HOST_WORKSPACE", str(ROOT / ".test_workspace"))

import sandbox.docker_host as docker_host_mod  # noqa: E402


class SnapshotPreflightTests(unittest.TestCase):
    def test_snapshot_preflight_failure_blocks_docker_commit(self) -> None:
        with patch.object(docker_host_mod, "_ensure_container_running", return_value=(True, "ok")), \
             patch.object(docker_host_mod, "_run_snapshot_preflight", return_value={
                 "ok": False,
                 "checks": [{"name": "stdout_cap_head_tail", "ok": False}],
             }), \
             patch.object(docker_host_mod, "_run_command") as run_mock:
            result = docker_host_mod.snapshot_container("blocked")

        self.assertFalse(result["ok"])
        self.assertIn("Snapshot preflight failed", result["error"])
        run_mock.assert_not_called()

    def test_snapshot_commit_runs_after_passing_preflight(self) -> None:
        commit_result = MagicMock(returncode=0, stdout="sha256:abc", stderr="")
        with patch.object(docker_host_mod, "_ensure_container_running", return_value=(True, "ok")), \
             patch.object(docker_host_mod, "_run_snapshot_preflight", return_value={
                 "ok": True,
                 "checks": [{"name": "supervisor_healthcheck", "ok": True}],
             }), \
             patch.object(docker_host_mod, "_run_command", return_value=commit_result) as run_mock:
            result = docker_host_mod.snapshot_container("passed")

        self.assertTrue(result["ok"])
        self.assertEqual(result["snapshot_image"], docker_host_mod.snapshot_image_name("passed"))
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.args[0][0:2], ["docker", "commit"])


if __name__ == "__main__":
    unittest.main()
