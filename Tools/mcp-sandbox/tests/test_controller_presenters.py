# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Smoke tests for legacy controller presenter helpers."""

from __future__ import annotations

import pytest

from sandbox.controller import dispatch  # noqa: F401 - import must succeed
from sandbox.presenters import present_grep_results, present_read_slice


@pytest.mark.unit
def test_present_read_slice_includes_line_window() -> None:
    text = present_read_slice(
        path="src/main.py",
        content="print('hi')\n",
        start_line=1,
        end_line=1,
        total_lines=10,
        size_bytes=12,
    )
    assert "src/main.py" in text
    assert "[lines 1-1]" in text
    assert "print('hi')" in text


@pytest.mark.unit
def test_present_grep_results_formats_matches() -> None:
    text = present_grep_results(
        matches=[{"path": "a.py", "line_number": 3, "line": "needle"}],
        pattern="needle",
        path=".",
    )
    assert "grep 'needle'" in text
    assert "a.py:3:needle" in text
