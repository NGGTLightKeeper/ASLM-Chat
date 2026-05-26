"""Head/tail truncation for command output returned to the model."""
from __future__ import annotations

import os

DEFAULT_HEAD_BYTES = 30 * 1024
DEFAULT_TAIL_BYTES = 30 * 1024


def _head_bytes() -> int:
    raw = os.environ.get("SANDBOX_OUTPUT_HEAD_BYTES", str(DEFAULT_HEAD_BYTES))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_HEAD_BYTES


def _tail_bytes() -> int:
    raw = os.environ.get("SANDBOX_OUTPUT_TAIL_BYTES", str(DEFAULT_TAIL_BYTES))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_TAIL_BYTES


def _slice_utf8(data: bytes, start: int, end: int | None = None) -> str:
    return data[start:end].decode("utf-8", errors="ignore")


def truncate_output(text: str | None) -> tuple[str, bool]:
    """Keep first/last byte windows; UTF-8 safe. Returns (text, was_truncated)."""
    if not text:
        return "", False

    encoded = text.encode("utf-8", errors="replace")
    head_b = _head_bytes()
    tail_b = _tail_bytes()
    budget = head_b + tail_b
    if len(encoded) <= budget:
        return text, False

    marker = (
        "\n\n"
        f"[output truncated: showed first {head_b} bytes and "
        f"last {tail_b} bytes of {len(encoded)} bytes]\n\n"
    )
    return (
        _slice_utf8(encoded, 0, head_b)
        + marker
        + _slice_utf8(encoded, len(encoded) - tail_b, None),
        True,
    )
