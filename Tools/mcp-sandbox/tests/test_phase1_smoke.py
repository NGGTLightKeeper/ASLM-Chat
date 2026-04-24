# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Quick smoke tests for Phase 1 changes."""

import os
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["SANDBOX_HOST_WORKSPACE"] = str(ROOT)

from sandbox import workspace
from sandbox.api import handle_tool
from sandbox.config import MAX_CAT_FILE_BYTES


def setup():
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


def test_large_file_auto_preview():
    # Must exceed MAX_CAT_FILE_BYTES (50KB) to trigger auto-preview
    content = "\n".join(f"def func_{i}(arg): return arg + {i}" for i in range(1, 4001))
    handle_tool("write", {"path": "big.py", "content": content})
    result = handle_tool("bash", {"command": "cat big.py"})

    stdout = result["result"]["stdout"]
    print("Output preview:")
    print(stdout[:600])
    print("...")
    assert result["ok"], f"Expected ok=True, got error: {result.get('error')}"
    assert "──" in stdout, "Missing metadata header"
    assert "next targets" in stdout, "Missing next targets"
    print("PASS: large file auto-preview")


def test_small_file_metadata_header():
    handle_tool("write", {"path": "small.txt", "content": "hello\nworld\n"})
    result = handle_tool("bash", {"command": "cat small.txt"})

    assert result["ok"]
    stdout = result["result"]["stdout"]
    assert "──" in stdout, "Missing metadata header"
    assert "small.txt" in stdout, "Missing path in header"
    print("PASS: small file metadata header")
    print(stdout)


def test_head_metadata():
    content = "\n".join(f"line{i}" for i in range(1, 101))
    handle_tool("write", {"path": "lines.txt", "content": content})
    result = handle_tool("bash", {"command": "head -n 5 lines.txt"})

    assert result["ok"]
    stdout = result["result"]["stdout"]
    assert "remaining" in stdout, "Missing remaining count"
    assert "lines.txt" in stdout, "Missing path"
    print("PASS: head with metadata")
    print(stdout)


def test_grep_with_few_results():
    handle_tool("write", {"path": "src/main.py", "content": "print('hello')\n"})
    handle_tool("write", {"path": "src/other.txt", "content": "HELLO\n"})
    result = handle_tool("bash", {"command": "grep -ri hello ."})

    assert result["ok"]
    stdout = result["result"]["stdout"]
    assert "grep:" in stdout.lower() or "hello" in stdout.lower()
    print("PASS: grep with few results")
    print(stdout)


def test_grep_clustered():
    # Create many files with matches to trigger clustering
    for i in range(40):
        handle_tool("write", {
            "path": f"pkg/file_{i}.py",
            "content": f"import foo\nfoo.bar()\nfoo.baz()\n",
        })
    result = handle_tool("bash", {"command": "grep -r foo pkg/"})

    assert result["ok"]
    stdout = result["result"]["stdout"]
    assert "densest files" in stdout or "grep:" in stdout.lower()
    print("PASS: grep clustering")
    print(stdout[:500])
    print("...")


if __name__ == "__main__":
    setup()
    tests = [
        test_large_file_auto_preview,
        test_small_file_metadata_header,
        test_head_metadata,
        test_grep_with_few_results,
        test_grep_clustered,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL: {t.__name__}: {e}")
            failed += 1
        print()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
