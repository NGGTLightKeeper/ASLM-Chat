# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import re
from pathlib import Path

from trafilatura.meta import reset_caches

from core.extract.content_processor import (
    _truncate_markdown_to_budget,
    compress_read_page_markdown,
)
from core.extract.page_normalizer import normalize_page


_FIXTURE = Path(__file__).parent / "fixtures" / "atomic_code_budget.html"
_URL = "https://fixture.test/atomic-budget"
_MARKERS = ("SMALL", "BOUNDARY", "OVERSIZED")


def _markdown() -> str:
    reset_caches()
    return normalize_page(_URL, _FIXTURE.read_text(encoding="utf-8"))


def _paired(output: str, marker: str) -> bool:
    return (f"SYNTH_{marker}_BEGIN" in output) == (f"SYNTH_{marker}_END" in output)


def _fences_balanced(output: str) -> bool:
    return len(re.findall(r"^[ \t]{0,3}(?:`{3,}|~{3,})", output, re.MULTILINE)) % 2 == 0


def _first_complete_budget(markdown: str, marker: str) -> int:
    needle = f"SYNTH_{marker}_BEGIN"
    low, high = 1, len(markdown) + 100
    while low < high:
        middle = (low + high) // 2
        if needle in _truncate_markdown_to_budget(markdown, middle):
            high = middle
        else:
            low = middle + 1
    return low


def test_atomic_thresholds_switch_without_partial_markers():
    markdown = _markdown()

    for marker in _MARKERS:
        threshold = _first_complete_budget(markdown, marker)
        below = _truncate_markdown_to_budget(markdown, threshold - 1)
        exact = _truncate_markdown_to_budget(markdown, threshold)

        assert _paired(below, marker)
        assert f"SYNTH_{marker}_BEGIN" not in below
        assert _paired(exact, marker)
        assert f"SYNTH_{marker}_BEGIN" in exact
        assert len(exact) <= threshold
        assert _fences_balanced(below)
        assert _fences_balanced(exact)


def test_skipped_code_does_not_discard_following_prose():
    markdown = _markdown()
    small_threshold = _first_complete_budget(markdown, "SMALL")

    output = _truncate_markdown_to_budget(markdown, small_threshold - 1)

    assert "SYNTH_SMALL_BEGIN" not in output
    assert "SYNTH_AFTER_SMALL" in output
    assert _fences_balanced(output)


def test_production_compactor_never_emits_partial_synthetic_blocks():
    markdown = _markdown()

    for budget in (500, 1_000, 1_243, 1_244, 4_000, 6_546, 6_547, 10_000, 20_000):
        output = compress_read_page_markdown(
            markdown,
            url=_URL,
            focus="",
            max_chars=budget,
            compress_threshold=1,
            compress_target=budget,
            enable_compress=True,
        )

        assert len(output) <= budget
        assert _fences_balanced(output)
        assert all(_paired(output, marker) for marker in _MARKERS)


def test_query_compactor_honors_budget_for_large_repetitive_code():
    markdown = _markdown()

    boundary = compress_read_page_markdown(
        markdown,
        url=_URL,
        focus="boundary_value compute_boundary",
        max_chars=6_000,
        compress_threshold=1,
        compress_target=6_000,
        enable_compress=True,
    )
    oversized = compress_read_page_markdown(
        markdown,
        url=_URL,
        focus="oversized_value compute_oversized",
        max_chars=14_000,
        compress_threshold=1,
        compress_target=14_000,
        enable_compress=True,
    )

    assert "SYNTH_BOUNDARY_BEGIN" in boundary
    assert "SYNTH_BOUNDARY_END" in boundary
    assert len(boundary) <= 6_000
    assert "SYNTH_OVERSIZED_BEGIN" in oversized
    assert "SYNTH_OVERSIZED_END" in oversized
    assert len(oversized) <= 14_000
