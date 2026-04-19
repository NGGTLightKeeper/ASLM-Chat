# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Small text helpers kept for script compatibility."""

from __future__ import annotations

import re


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\x00", " ")).strip()


def sanitize_content(text: str) -> str:
    cleaned = (text or "").replace("\x00", " ")
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)
    return cleaned.strip()
