# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Compact presentation helpers for supervised file previews."""

from __future__ import annotations

import os
import re

from sandbox.config import MAX_FILE_MAP_SYMBOLS


_STRUCTURE_RE = re.compile(
    r"^(\s{0,4})"
    r"(?:(?:pub(?:\(crate\))?\s+)?)"
    r"(?:(?:export\s+(?:default\s+)?)?)"
    r"(?:async\s+)?"
    r"(?:static\s+)?"
    r"(?:abstract\s+)?"
    r"(class|def|function|func|fn|struct|enum|trait|impl|"
    r"interface|module|type|namespace|mod)"
    r"\s+(\w+)"
)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")

_CODE_EXTENSIONS = frozenset({
    ".c", ".cc", ".cpp", ".cs", ".go", ".java", ".js", ".jsx", ".kt",
    ".mjs", ".php", ".py", ".rs", ".scala", ".swift", ".ts", ".tsx",
})
_TEXT_EXTENSIONS = frozenset({
    ".cfg", ".conf", ".csv", ".css", ".html", ".ini", ".json", ".less",
    ".log", ".markdown", ".md", ".rst", ".scss", ".sql", ".toml", ".tsv",
    ".txt", ".xml", ".yaml", ".yml",
})


def _human_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _extract_code_structure(lines: list[str]) -> list[dict[str, object]]:
    symbols: list[dict[str, object]] = []
    for index, line in enumerate(lines, 1):
        match = _STRUCTURE_RE.match(line)
        if not match:
            continue
        symbols.append(
            {
                "line": index,
                "indent": len(match.group(1)),
                "kind": match.group(2),
                "name": match.group(3),
            }
        )
        if len(symbols) >= MAX_FILE_MAP_SYMBOLS:
            break
    return symbols


def _extract_markdown_headings(lines: list[str]) -> list[dict[str, object]]:
    headings: list[dict[str, object]] = []
    for index, line in enumerate(lines, 1):
        match = _HEADING_RE.match(line)
        if match:
            headings.append(
                {
                    "line": index,
                    "level": len(match.group(1)),
                    "text": match.group(2).strip(),
                }
            )
    return headings


def _extract_text_landmarks(lines: list[str], max_landmarks: int = 12) -> list[dict[str, object]]:
    if not lines:
        return []
    landmarks: list[dict[str, object]] = [{"line": 1, "text": lines[0].rstrip()[:80]}]
    if len(lines) > 2:
        step = max(1, len(lines) // max_landmarks)
        for index in range(step, len(lines) - 1, step):
            text = lines[index].rstrip()[:80]
            if text.strip():
                landmarks.append({"line": index + 1, "text": text})
            if len(landmarks) >= max_landmarks - 1:
                break
    if len(lines) > 1:
        landmarks.append({"line": len(lines), "text": lines[-1].rstrip()[:80]})
    return landmarks


def _present_code_preview(
    path: str,
    head_lines: list[str],
    total_lines: int,
    size_bytes: int,
    tail_lines: list[str] | None,
    tail_start_line: int,
) -> str:
    parts = [f"-- {path} ({total_lines} lines, {_human_size(size_bytes)}) --"]
    symbols = _extract_code_structure(head_lines)
    if symbols:
        parts.append("\n[structure]")
        for symbol in symbols:
            pad = " " * (int(symbol["indent"]) // 2)
            parts.append(f"  L{symbol['line']:<6} {pad}{symbol['kind']} {symbol['name']}")

    head_end = min(30, len(head_lines), total_lines)
    if head_end:
        parts.append(f"\n[head: 1-{head_end}]")
        parts.append("\n".join(head_lines[:head_end]))

    if tail_lines and tail_start_line:
        parts.append(f"\n[tail: {tail_start_line}-{total_lines}]")
        parts.append("\n".join(tail_lines))

    parts.append("\n[next]")
    if symbols:
        for symbol in symbols[:3]:
            start = int(symbol["line"])
            parts.append(f"  cat {path} | sed -n '{start},{min(start + 60, total_lines)}p'")
    else:
        mid = max(1, total_lines // 2)
        parts.append(f"  cat {path} | sed -n '{mid},{min(mid + 80, total_lines)}p'")
    return "\n".join(parts)


def _present_text_preview(
    path: str,
    head_lines: list[str],
    total_lines: int,
    size_bytes: int,
    tail_lines: list[str] | None,
    tail_start_line: int,
) -> str:
    parts = [f"-- {path} ({total_lines} lines, {_human_size(size_bytes)}) --"]
    ext = os.path.splitext(path)[1].lower()
    landmarks = (
        _extract_markdown_headings(head_lines)
        if ext in {".md", ".markdown", ".rst"}
        else _extract_text_landmarks(head_lines)
    )
    if landmarks:
        parts.append("\n[landmarks]")
        for landmark in landmarks[:12]:
            text = str(landmark.get("text", ""))
            parts.append(f"  L{landmark['line']:<6} {text}")

    head_end = min(30, len(head_lines), total_lines)
    if head_end:
        parts.append(f"\n[head: 1-{head_end}]")
        parts.append("\n".join(head_lines[:head_end]))

    if tail_lines and tail_start_line:
        parts.append(f"\n[tail: {tail_start_line}-{total_lines}]")
        parts.append("\n".join(tail_lines))

    parts.append("\n[next]")
    mid = max(1, total_lines // 2)
    parts.append(f"  cat {path} | sed -n '{mid},{min(mid + 80, total_lines)}p'")
    return "\n".join(parts)


def present_auto_preview(
    path: str,
    head_lines: list[str],
    total_lines: int,
    size_bytes: int,
    mime: str,
    kind: str = "text",
    tail_lines: list[str] | None = None,
    tail_start_line: int = 0,
) -> str:
    if kind != "text" or not head_lines:
        return f"[{kind} file: {mime}, {_human_size(size_bytes)}]"

    ext = os.path.splitext(path)[1].lower()
    if ext in _CODE_EXTENSIONS or (
        ext not in _TEXT_EXTENSIONS and _extract_code_structure(head_lines[:120])
    ):
        return _present_code_preview(
            path, head_lines, total_lines, size_bytes, tail_lines, tail_start_line
        )
    return _present_text_preview(
        path, head_lines, total_lines, size_bytes, tail_lines, tail_start_line
    )
