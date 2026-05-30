# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ.setdefault("SANDBOX_HOST_WORKSPACE", str(ROOT))

from sandbox import workspace  # noqa: E402
from sandbox.api import handle_tool  # noqa: E402
from sandbox.config import DEFAULT_TASK_DIR  # noqa: E402


# Build a fake exec_bash return value.
def _mock_exec(stdout: str = "", stderr: str = "", exit_code: int = 0, cwd: str = "."):
    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "error": None if exit_code == 0 else f"Exit code: {exit_code}",
        "elapsed_ms": 1,
        "truncated": False,
        "cwd": cwd,
    }


class CwdContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task_root = workspace.task_root()
        self.task_root.mkdir(parents=True, exist_ok=True)
        for child in list(self.task_root.iterdir()):
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except PermissionError:
                pass

    # pwd reports correct container path.

    def test_pwd_at_root_reports_task_root(self) -> None:
        with patch("sandbox.api.exec_bash", return_value=_mock_exec(stdout=f"/workspace/{DEFAULT_TASK_DIR}\n")) as mock:
            result = handle_tool("bash", {"command": "pwd"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["stdout"], f"/workspace/{DEFAULT_TASK_DIR}\n")
        mock.assert_called_once()

    def test_pwd_with_subdir_cwd_reports_subdir(self) -> None:
        handle_tool("write", {"path": "repo/file.txt", "content": "x"})
        with patch("sandbox.api.exec_bash", return_value=_mock_exec(stdout=f"/workspace/{DEFAULT_TASK_DIR}/repo\n", cwd="repo")) as mock:
            result = handle_tool("bash", {"command": "pwd", "cwd": "repo"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["stdout"], f"/workspace/{DEFAULT_TASK_DIR}/repo\n")
        mock.assert_called_once()

    # cwd argument is respected.

    def test_routed_command_respects_explicit_cwd(self) -> None:
        handle_tool("write", {"path": "src/app.py", "content": "print('hi')\n"})
        result = handle_tool("bash", {"command": "cat app.py", "cwd": "src"})
        self.assertTrue(result["ok"])
        self.assertIn("hi", result["result"]["stdout"])
        self.assertEqual(result["result"]["cwd"], "src")

    def test_cwd_returned_matches_input_cwd(self) -> None:
        handle_tool("write", {"path": "lib/util.py", "content": "x = 1\n"})
        result = handle_tool("bash", {"command": "cat util.py", "cwd": "lib"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["cwd"], "lib")

    # Passing cwd=None should be treated as '.'.
    def test_none_cwd_defaults_to_root(self) -> None:
        with patch(
            "sandbox.api.exec_bash",
            return_value=_mock_exec(stdout="ok\n"),
        ) as mock:
            handle_tool("bash", {"command": "echo ok | cat", "cwd": None})
        mock.assert_called_once()
        self.assertEqual(mock.call_args.kwargs["cwd"], ".")

    # Container-space paths fall through to real bash.

    # `cat /etc/os-release` must NOT be handled by the workspace controller.
    def test_cat_container_absolute_path_falls_through(self) -> None:
        with patch(
            "sandbox.api.exec_bash",
            return_value=_mock_exec(stdout="NAME=Linux\n"),
        ) as mock:
            result = handle_tool("bash", {"command": "cat /etc/os-release"})

        # Must have fallen through — exec_bash was called
        mock.assert_called_once()
        # Must not be routed via workspace controller
        self.assertFalse(
            result.get("result", {}).get("routed", False),
            "cat /etc/os-release should not be workspace-routed",
        )

    # `ls /usr/bin` must fall through to real bash.
    def test_ls_container_absolute_path_falls_through(self) -> None:
        with patch(
            "sandbox.api.exec_bash",
            return_value=_mock_exec(stdout="python3\nbash\n"),
        ) as mock:
            result = handle_tool("bash", {"command": "ls /usr/bin"})

        mock.assert_called_once()
        self.assertFalse(
            result.get("result", {}).get("routed", False),
            "ls /usr/bin should not be workspace-routed",
        )

    # cd inside command does not persist across calls.

    # `cd / && ls` goes to real bash; next call still uses task_cwd.
    def test_cd_slash_does_not_affect_next_call_cwd(self) -> None:
        handle_tool("write", {"path": "marker.txt", "content": "here"})

        with patch("sandbox.api.exec_bash", return_value=_mock_exec(stdout="bin etc\n")):
            handle_tool("bash", {"command": "cd / && ls"})

        # Next call with no cwd specified — should still find marker.txt at root
        result = handle_tool("bash", {"command": "cat marker.txt"})
        self.assertTrue(result["ok"])
        self.assertIn("here", result["result"]["stdout"])
        self.assertEqual(result["result"]["cwd"], ".")

    # Each call is independent; cwd comes from the argument, not session.
    def test_consecutive_routed_calls_use_explicit_cwd(self) -> None:
        handle_tool("write", {"path": "a/b/file.txt", "content": "deep"})

        with patch("sandbox.api.exec_bash", return_value=_mock_exec(stdout="b\n", cwd="a")):
            r1 = handle_tool("bash", {"command": "ls .", "cwd": "a"})
        self.assertTrue(r1["ok"])
        self.assertIn("b", r1["result"]["stdout"])
        self.assertEqual(r1["result"]["cwd"], "a")

        r2 = handle_tool("bash", {"command": "cat file.txt", "cwd": "a/b"})
        self.assertTrue(r2["ok"])
        self.assertIn("deep", r2["result"]["stdout"])
        self.assertEqual(r2["result"]["cwd"], "a/b")

    # Workspace-relative subdir cd updates cwd correctly.

    # Passing cwd='src/lib' resolves path inside task_root.
    def test_cwd_subdir_resolves_correctly(self) -> None:
        handle_tool("write", {"path": "src/lib/mod.py", "content": "MOD\n"})
        result = handle_tool("bash", {"command": "cat mod.py", "cwd": "src/lib"})
        self.assertTrue(result["ok"])
        self.assertIn("MOD", result["result"]["stdout"])
        self.assertEqual(result["result"]["cwd"], "src/lib")

    # Traversal via cwd is blocked.

    # cwd='../../etc' must not allow reading outside task_root.
    def test_cwd_traversal_is_blocked(self) -> None:
        result = handle_tool("bash", {"command": "ls .", "cwd": "../../etc"})
        # Must either fail or fall through to container where it also fails
        if result.get("ok"):
            # If somehow ok, must not have escaped
            stdout = result.get("result", {}).get("stdout", "")
            self.assertNotIn("passwd", stdout, "cwd traversal escaped to /etc!")


if __name__ == "__main__":
    unittest.main()
