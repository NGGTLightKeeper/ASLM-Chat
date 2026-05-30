# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import pytest

from browser import (
    _build_parsed_state,
    _filter_snapshot_controls,
    _format_control_line,
    _format_parsed_controls,
    _is_noise_element,
    is_browser_closed_error,
)


@pytest.mark.unit
def test_is_noise_element_filters_empty_links_outside_main() -> None:
    assert _is_noise_element({"role": "link", "name": "", "landmark": "contentinfo"})
    assert not _is_noise_element(
        {"role": "button", "name": "Submit", "landmark": "main"},
    )


@pytest.mark.unit
def test_format_control_line_includes_editable_and_region() -> None:
    line = _format_control_line(
        {
            "ref": "e3",
            "role": "textbox",
            "name": "Search",
            "value": "cats",
            "landmark": "main",
            "interactive": True,
        }
    )
    assert "[e3]" in line
    assert "textbox" in line
    assert "editable" in line
    assert 'region=main' in line


@pytest.mark.unit
def test_filter_snapshot_controls_hides_noise_in_compact_mode() -> None:
    elements = [
        {"ref": "e0", "role": "button", "name": "Go", "interactive": True, "landmark": "main"},
        {"ref": "e1", "role": "link", "name": "", "interactive": True, "landmark": "contentinfo"},
    ]
    compact = _filter_snapshot_controls(elements, full=False)
    refs = {item["ref"] for item in compact}
    assert refs == {"e0"}
    full = _filter_snapshot_controls(elements, full=True)
    assert len(full) == 2


@pytest.mark.unit
def test_format_parsed_controls_groups_and_caps_items() -> None:
    elements = [
        {"ref": "e0", "role": "textbox", "name": "Query", "interactive": True, "landmark": "main"},
        {"ref": "e1", "role": "button", "name": "Search", "interactive": True, "landmark": "main"},
        {"ref": "e2", "role": "link", "name": "Docs", "interactive": True, "landmark": "main"},
    ]
    lines = _format_parsed_controls(elements, full=False, max_items=2)
    joined = "\n".join(lines)
    assert "Text inputs" in joined
    assert "more controls hidden" in joined


@pytest.mark.unit
def test_build_parsed_state_reports_counts() -> None:
    elements = [
        {"ref": "e0", "role": "textbox", "name": "Query", "interactive": True, "landmark": "main"},
        {"ref": "e1", "role": "button", "name": "Search", "interactive": True, "landmark": "main"},
    ]
    state = _build_parsed_state(elements, full=False, max_items=10)
    assert state["mode"] == "controls"
    assert state["counts"]["visible_controls"] == 2
    assert state["counts"]["text_inputs"] == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "message",
    [
        "Target page, context or browser has been closed",
        "Connection closed while reading from the driver",
    ],
)
def test_is_browser_closed_error(message: str) -> None:
    assert is_browser_closed_error(RuntimeError(message))
