# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "supervisor"
SRC = ROOT / "src"
for path in (SUPERVISOR, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
os.environ["SANDBOX_HOST_WORKSPACE"] = str(ROOT)

from sandbox.session_state import get_session_state, reset_session_state  # noqa: E402
import sandbox.session_state as session_state_mod  # noqa: E402


def test_state_tracks_touches():
    reset_session_state()
    state = get_session_state()

    state.record_touch("track.py", "open")
    state.record_touch("track.py", "open")

    assert state.touched_paths.get("track.py", 0) == 2


def test_state_tracks_searches():
    reset_session_state()
    state = get_session_state()

    state.record_search("hello", ".", 2)

    assert state.last_searches
    assert state.last_searches[-1]["pattern"] == "hello"
    assert state.last_searches[-1]["hit_count"] == 2


def test_loop_detection():
    reset_session_state()
    state = get_session_state()

    state.record_touch("loop.py", "open")
    state.record_touch("loop.py", "open")
    state.record_touch("loop.py", "open")

    assert state.should_break_loop("loop.py", "open")
    assert not state.should_break_loop("other.py", "open")


def test_unread_windows():
    reset_session_state()
    state = get_session_state()

    state.record_touch("file.py", "open", window=(1, 50))
    state.record_touch("file.py", "open", window=(80, 120))

    unread = state.get_unread_windows("file.py", 200)
    assert any(start == 51 for start, _end in unread)
    assert any(end == 200 for _start, end in unread)


def test_read_overlap():
    reset_session_state()
    state = get_session_state()

    state.record_touch("ov.py", "open", window=(1, 100))

    assert state.get_read_overlap("ov.py", 1, 100) == 1.0
    assert 0.4 < state.get_read_overlap("ov.py", 50, 150) < 0.6
    assert state.get_read_overlap("ov.py", 101, 200) == 0.0


def test_state_caps_long_lived_path_memory(monkeypatch):
    reset_session_state()
    monkeypatch.setattr(session_state_mod, "MAX_TRACKED_PATHS", 3)
    monkeypatch.setattr(session_state_mod, "MAX_LOOP_COUNTERS", 4)
    monkeypatch.setattr(session_state_mod, "MAX_READ_WINDOWS_PER_PATH", 2)
    monkeypatch.setattr(session_state_mod, "MAX_REPRESENTATIONS_PER_PATH", 2)
    state = get_session_state()

    for index in range(10):
        state.record_touch(
            f"file_{index}.py",
            "open",
            window=(index + 1, index + 1),
            representation="raw",
        )

    assert len(state.touched_paths) <= 3
    assert len(state.read_windows) <= 3
    assert len(state.loop_counters) <= 4
    assert len(state.representations_served) <= 3

    state.record_touch("hot.py", "open", window=(1, 1), representation="raw")
    state.record_touch("hot.py", "open", window=(2, 2), representation="map")
    state.record_touch("hot.py", "open", window=(3, 3), representation="outline")

    assert state.read_windows["hot.py"] == [(2, 2), (3, 3)]
    assert state.representations_served["hot.py"] == ["map", "outline"]
