# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import reset_task_root  # noqa: E402
from sandbox.api import handle_tool  # noqa: E402
import sandbox.container as container_mod  # noqa: E402


class BackgroundPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_task_root()

    def test_auto_does_not_background_short_simple_command(self) -> None:
        self.assertFalse(container_mod.should_use_background("echo ok", timeout_s=1, background="auto"))

    def test_auto_backgrounds_long_running_pattern(self) -> None:
        self.assertTrue(container_mod.should_use_background("pytest -x", timeout_s=1, background="auto"))

    def test_auto_backgrounds_timeout_threshold(self) -> None:
        self.assertTrue(container_mod.should_use_background("echo ok", timeout_s=10, background="auto"))

    def test_never_and_always_override_auto(self) -> None:
        self.assertFalse(container_mod.should_use_background("pytest -x", timeout_s=60, background="never"))
        self.assertTrue(container_mod.should_use_background("echo ok", timeout_s=1, background="always"))

    def test_api_passes_background_argument_to_exec(self) -> None:
        with patch(
            "sandbox.api.exec_bash",
            return_value={
                "exit_code": 0,
                "stdout": "ok\n",
                "stderr": "",
                "error": None,
                "elapsed_ms": 1,
                "truncated": False,
                "cwd": ".",
            },
        ) as exec_mock:
            result = handle_tool("bash", {"command": "echo ok | cat", "background": "never"})

        self.assertTrue(result["ok"])
        self.assertEqual(exec_mock.call_args.kwargs["background"], "never")

    def test_routed_ls_does_not_reach_exec(self) -> None:
        with patch("sandbox.api.exec_bash") as exec_mock:
            result = handle_tool("bash", {"command": "ls", "background": "always"})

        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["routed"])
        exec_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
