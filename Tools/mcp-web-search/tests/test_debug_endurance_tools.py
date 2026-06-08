# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from core.debug.web_search_searxng_compare import _domains, _summary
from core.debug.web_search_stress import _consecutive_failures


def test_compare_summary_tracks_both_backends() -> None:
    rows = [
        {
            "backend": "core",
            "status": "done",
            "elapsed_sec": 1.0,
            "result_count": 3,
            "read_count": 2,
            "read_chars": 100,
        },
        {
            "backend": "legacy_searxng",
            "status": "error",
            "elapsed_sec": 2.0,
            "result_count": 0,
            "read_count": 0,
            "read_chars": 0,
        },
    ]

    summary = _summary(rows)

    assert summary["core"]["successful"] == 1
    assert summary["legacy_searxng"]["empty_or_error"] == 1


def test_domains_normalizes_www_and_consecutive_failures() -> None:
    assert _domains(["https://www.example.com/a", "https://example.com/b"]) == {"example.com"}
    assert _consecutive_failures([{"success": True}, {"success": False}, {"success": False}]) == 2
    assert _consecutive_failures([{"success": False}, {"success": False}]) == 2
