# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Integration tests: compound pipeline bypass normalization.

Verifies that common syntax bypasses are now intercepted by the
intent controller and return structured output.
"""

import os
import sys
import shutil
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["SANDBOX_HOST_WORKSPACE"] = str(ROOT)

from sandbox import workspace
from sandbox.api import handle_tool
from sandbox.session_state import reset_session_state


def setup():
    reset_session_state()
    task = workspace.task_root()
    task.mkdir(parents=True, exist_ok=True)
    for c in list(task.iterdir()):
        if c.name in ("clone_test", "curl_test", "downloads"):
            continue
        try:
            if c.is_dir():
                shutil.rmtree(c, ignore_errors=True)
            else:
                c.unlink(missing_ok=True)
        except Exception:
            pass


def test_cat_pipe_head_is_routed():
    """cat file | head -n 10 is intercepted and returns structured OPEN output."""
    content = "\n".join(f"line_{i}" for i in range(1, 51))
    handle_tool("write", {"path": "data.txt", "content": content})

    result = handle_tool("bash", {"command": "cat data.txt | head -n 10"})
    assert result["ok"], f"Expected ok=True, got: {result.get('error')}"
    stdout = result["result"]["stdout"]
    assert "data.txt" in stdout, "Missing filename in output"
    assert "line_1" in stdout, "Missing content"
    assert "line_11" not in stdout, "Should only show first 10 lines"
    print("PASS: cat file | head -n 10 → structured OPEN [1:10]")
    print(stdout)


def test_cat_pipe_grep_is_routed():
    """cat file | grep pattern is intercepted and returns LOCATE output."""
    content = "hello world\nfoo bar\nhello again\nbaz\n"
    handle_tool("write", {"path": "search.txt", "content": content})

    result = handle_tool("bash", {"command": "cat search.txt | grep hello"})
    assert result["ok"], f"Expected ok=True, got: {result.get('error')}"
    stdout = result["result"]["stdout"]
    assert "hello" in stdout.lower(), "Missing search results"
    print("PASS: cat file | grep pattern → structured LOCATE")
    print(stdout)


def test_sed_range_bypass_is_routed():
    """sed -n '5,10p' file is handled as OPEN with line range."""
    content = "\n".join(f"row_{i}" for i in range(1, 31))
    handle_tool("write", {"path": "rows.txt", "content": content})

    result = handle_tool("bash", {"command": "sed -n '5,10p' rows.txt"})
    assert result["ok"], f"Expected ok=True"
    stdout = result["result"]["stdout"]
    assert "row_5" in stdout, "Missing row_5"
    assert "row_10" in stdout, "Missing row_10"
    assert "row_11" not in stdout, "Should stop at row_10"
    print("PASS: sed -n '5,10p' → OPEN [5:10]")
    print(stdout)


def test_chains_still_go_to_real_bash():
    """&&, ||, ; constructs are not intercepted."""
    # These should NOT have routed=True
    # (they go to real bash which may fail without container)
    chain_cases = [
        "echo hello && cat data.txt",
        "cat data.txt || echo failed",
    ]
    for cmd in chain_cases:
        with patch(
            "sandbox.api.exec_bash",
            return_value={
                "exit_code": 0,
                "stdout": "mocked real bash\n",
                "stderr": "",
                "error": None,
                "elapsed_ms": 1,
                "truncated": False,
                "cwd": ".",
            },
        ) as exec_mock:
            result = handle_tool("bash", {"command": cmd})
        # Key: should not be routed through our controllers
        assert not result.get("result", {}).get("routed", False), (
            f"Compound chain should not be routed: {cmd}"
        )
        exec_mock.assert_called_once()
    print(f"PASS: {len(chain_cases)} chain commands not intercepted")


if __name__ == "__main__":
    setup()
    tests = [
        test_cat_pipe_head_is_routed,
        test_cat_pipe_grep_is_routed,
        test_sed_range_bypass_is_routed,
        test_chains_still_go_to_real_bash,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            import traceback
            print(f"FAIL: {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1
        print()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
