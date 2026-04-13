# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Shared text utilities for the deep-research pipeline."""


def compact_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def sanitize_content(text: str) -> str:
    return (text or "").replace("\x00", "").strip()
