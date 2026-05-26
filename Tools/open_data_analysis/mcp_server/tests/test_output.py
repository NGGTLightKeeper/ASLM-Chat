"""Tests for head/tail output truncation."""
from __future__ import annotations

import pytest

from sandbox_mcp.output import truncate_output


def test_short_output_unchanged():
    text, truncated = truncate_output("hello\n")
    assert text == "hello\n"
    assert truncated is False


def test_long_output_head_tail(monkeypatch):
    monkeypatch.setenv("SANDBOX_OUTPUT_HEAD_BYTES", "100")
    monkeypatch.setenv("SANDBOX_OUTPUT_TAIL_BYTES", "100")

    marker_line = "\n<<<MIDDLE>>>\n"
    body = ("A" * 40_000) + marker_line + ("Z" * 40_000)
    text, truncated = truncate_output(body)

    assert truncated is True
    assert "[output truncated:" in text
    assert "bytes of" in text
    assert marker_line not in text
    assert text.startswith("A")
    assert text.rstrip().endswith("Z")


def test_utf8_boundary_safe():
    text = "ы" * 50_000  # multi-byte cyrillic
    out, truncated = truncate_output(text)
    assert truncated is True
    assert out.encode("utf-8", errors="replace")  # round-trip safe


