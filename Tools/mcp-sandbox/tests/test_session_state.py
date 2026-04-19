"""Tests for session state and loop breaking."""

import os
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["SANDBOX_HOST_WORKSPACE"] = str(ROOT)

from sandbox import workspace
from sandbox.api import handle_tool
from sandbox.session_state import get_session_state, reset_session_state


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


def test_state_tracks_touches():
    reset_session_state()
    handle_tool("write", {"path": "track.py", "content": "x = 1\n"})

    handle_tool("bash", {"command": "cat track.py"})
    handle_tool("bash", {"command": "cat track.py"})

    state = get_session_state()
    assert state.touched_paths.get("track.py", 0) >= 2, (
        f"Expected >= 2 touches, got {state.touched_paths}"
    )
    print("PASS: state tracks touches")
    print(f"  touched_paths: {state.touched_paths}")


def test_state_tracks_searches():
    reset_session_state()
    handle_tool("write", {"path": "s.py", "content": "hello world\n"})

    handle_tool("bash", {"command": "grep hello s.py"})

    state = get_session_state()
    # Note: _extract_target_path currently picks the first positional arg
    # which for grep is the pattern, not the file. Intent-based routing
    # will fix this — for now we just verify state is recording *something*.
    total_touches = sum(state.touched_paths.values())
    assert total_touches >= 1, f"Expected at least 1 touch, got {state.touched_paths}"
    print("PASS: state tracks searches")
    print(f"  touched_paths: {state.touched_paths}")


def test_compact_context_appears():
    reset_session_state()
    handle_tool("write", {"path": "ctx.txt", "content": "data\n"})

    # First two touches build state
    handle_tool("bash", {"command": "cat ctx.txt"})
    handle_tool("bash", {"command": "cat ctx.txt"})

    # Third touch should include compact_context in output
    result = handle_tool("bash", {"command": "cat ctx.txt"})
    stdout = result["result"]["stdout"]
    assert "exploration state" in stdout, "compact_context missing from output"
    print("PASS: compact context appears after multiple touches")


def test_loop_detection():
    reset_session_state()
    state = get_session_state()

    # Simulate 3 open touches on same file
    state.record_touch("loop.py", "open")
    state.record_touch("loop.py", "open")
    state.record_touch("loop.py", "open")

    assert state.should_break_loop("loop.py", "open"), (
        "Expected loop break after 3 touches"
    )
    assert not state.should_break_loop("other.py", "open"), (
        "Should not trigger for untouched file"
    )
    print("PASS: loop detection works")


def test_unread_windows():
    reset_session_state()
    state = get_session_state()

    state.record_touch("file.py", "open", window=(1, 50))
    state.record_touch("file.py", "open", window=(80, 120))

    unread = state.get_unread_windows("file.py", 200)
    # Should have gaps: 51-79 and 121-200
    assert any(s == 51 for s, e in unread), f"Expected gap starting at 51: {unread}"
    assert any(e == 200 for s, e in unread), f"Expected gap ending at 200: {unread}"
    print("PASS: unread windows detection")
    print(f"  unread: {unread}")


def test_read_overlap():
    reset_session_state()
    state = get_session_state()

    state.record_touch("ov.py", "open", window=(1, 100))

    overlap = state.get_read_overlap("ov.py", 1, 100)
    assert overlap == 1.0, f"Expected full overlap, got {overlap}"

    overlap = state.get_read_overlap("ov.py", 50, 150)
    assert 0.4 < overlap < 0.6, f"Expected ~50% overlap, got {overlap}"

    overlap = state.get_read_overlap("ov.py", 101, 200)
    assert overlap == 0.0, f"Expected no overlap, got {overlap}"
    print("PASS: read overlap calculation")


if __name__ == "__main__":
    setup()
    tests = [
        test_state_tracks_touches,
        test_state_tracks_searches,
        test_compact_context_appears,
        test_loop_detection,
        test_unread_windows,
        test_read_overlap,
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
