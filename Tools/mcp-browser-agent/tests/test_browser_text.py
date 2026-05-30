# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import pytest

from browser_text import (
    _css_string,
    _infer_action,
    _next_text,
    _parse_line_range,
    _replace_match,
    replace_line_range,
)


# _parse_line_range — replace, insert-after-end, and out-of-range errors.

@pytest.mark.unit
def test_parse_line_range_replace_and_insert_modes() -> None:
    assert _parse_line_range("2:3", 5) == (2, 3, False)
    with pytest.raises(ValueError, match="outside text"):
        _parse_line_range("9:10", 5)
    assert _parse_line_range("6:5", 5) == (6, 5, True)


# replace_line_range — in-place replace and append insert.

@pytest.mark.unit
def test_replace_line_range_replaces_and_inserts() -> None:
    current = "line1\nline2\nline3\n"
    replaced = replace_line_range(current, "2:2", "MIDDLE")
    assert replaced.splitlines() == ["line1", "MIDDLE", "line3"]

    inserted = replace_line_range("a\nb\n", "3:2", "NEW")
    assert inserted.splitlines() == ["a", "b", "NEW"]


# _infer_action — map tool args to read/replace/set/delete.

@pytest.mark.unit
@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ({"action": "read"}, "read"),
        ({"old_text": "x", "new_text": "y"}, "replace"),
        ({"text": "hello"}, "set"),
        ({"range": "1:1"}, "delete"),
    ],
)
def test_infer_action(args: dict, expected: str) -> None:
    assert _infer_action(args) == expected


# _replace_match — unique match required unless replace_all.

@pytest.mark.unit
def test_replace_match_requires_unique_match_without_replace_all() -> None:
    assert _replace_match("only foo here", "foo", "bar", False) == "only bar here"
    with pytest.raises(ValueError, match="found 2 times"):
        _replace_match("foo foo", "foo", "bar", False)
    assert _replace_match("foo foo", "foo", "bar", True) == "bar bar"


# _next_text — set, replace, and delete action payloads.

@pytest.mark.unit
def test_next_text_set_replace_and_delete() -> None:
    assert _next_text("set", {"text": "NEW"}, "OLD") == "NEW"
    assert _next_text("replace", {"old_text": "OLD", "new_text": "NEW"}, "OLD") == "NEW"
    assert _next_text("delete", {"all": True}, "OLD") == ""


# _css_string — escape double quotes for CSS selectors.

@pytest.mark.unit
def test_css_string_escapes_quotes() -> None:
    assert _css_string('say "hi"') == r'"say \"hi\""'
