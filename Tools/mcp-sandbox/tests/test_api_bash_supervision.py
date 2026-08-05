# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import shutil
from unittest.mock import patch

import pytest

from sandbox.api import handle_tool
from sandbox.workspace import task_root


# Autouse fixture: reset task_root before and after each test.

@pytest.fixture(autouse=True)
def _clean_task_root() -> None:
    task = task_root()
    task.mkdir(parents=True, exist_ok=True)
    for child in list(task.iterdir()):
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    yield
    for child in list(task.iterdir()):
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


# Plain cat on a large workspace file uses structured preview with paging markers.

@pytest.mark.unit
def test_plain_cat_large_file_uses_structured_preview() -> None:
    content = "\n".join(f"def func_{i}(): pass" for i in range(4000))
    handle_tool("write", {"path": "big.py", "content": content})
    result = handle_tool("bash", {"command": "cat big.py"})
    stdout = result["result"]["stdout"]
    assert result["ok"]
    assert "-- big.py" in stdout
    assert "[next]" in stdout


# grep must route to exec_bash, not the legacy workspace controller.

@pytest.mark.unit
def test_grep_routes_to_real_bash_not_legacy_controller() -> None:
    handle_tool("write", {"path": "needle.txt", "content": "needle\n"})
    with patch(
        "sandbox.api.exec_bash",
        return_value={
            "exit_code": 0,
            "stdout": "needle.txt:needle\n",
            "stderr": "",
            "error": None,
            "elapsed_ms": 3,
            "truncated": False,
            "cwd": ".",
        },
    ) as exec_bash:
        result = handle_tool("bash", {"command": "grep -r needle ."})
    exec_bash.assert_called_once()
    assert result["ok"]
    assert not result["result"].get("routed", False)


# Compound shell commands must never take the single-file preview shortcut.

@pytest.mark.unit
def test_compound_shell_command_never_uses_file_preview_shortcut() -> None:
    handle_tool("write", {"path": "a.txt", "content": "x\n"})
    with patch(
        "sandbox.api.exec_bash",
        return_value={
            "exit_code": 0,
            "stdout": "ok\n",
            "stderr": "",
            "error": None,
            "elapsed_ms": 2,
            "truncated": False,
            "cwd": ".",
        },
    ) as exec_bash:
        result = handle_tool("bash", {"command": "cat a.txt && echo done"})
    exec_bash.assert_called_once()
    assert result["ok"]
