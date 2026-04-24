# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Presentation layer for sandbox tool responses.

Transforms raw backend data into structured, navigable representations
that help the model make better exploration decisions instead of
dumping raw text.

Six universal representations:
  raw_slice         — small file / specific range with metadata header
  file_map          — structural map for large code files
  segmented_outline — landmarks for docs/logs/text
  search_hits       — flat or clustered grep results
  reference_map     — symbol trace results (future)
  metadata_only     — stat/file/wc compact card
"""

from __future__ import annotations

import os
import re
from typing import Any

from sandbox.config import (
    GREP_CLUSTER_THRESHOLD,
    MAX_FILE_MAP_SYMBOLS,
    RG_TYPE_TO_GLOB,
)


# ── Structure extraction ────────────────────────────────────────────

# Universal regex for common code constructs (low-indentation definitions)
_STRUCTURE_RE = re.compile(
    r"^(\s{0,4})"  # max 1 indent level
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

_TEXT_EXTENSIONS = frozenset({
    ".md", ".markdown", ".rst", ".txt", ".log", ".csv", ".tsv",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".xml",
    ".html", ".css", ".scss", ".less", ".sql", ".json",
})

_CODE_EXTENSIONS: frozenset[str] = frozenset(
    "." + glob[2:]
    for glob in set(RG_TYPE_TO_GLOB.values())
    if glob.startswith("*.")
) - _TEXT_EXTENSIONS


def _extract_code_structure(
    lines: list[str],
    max_symbols: int = MAX_FILE_MAP_SYMBOLS,
) -> list[dict[str, Any]]:
    """Extract structural landmarks (class/def/func) from code lines."""

    symbols: list[dict[str, Any]] = []
    for i, line in enumerate(lines, 1):
        m = _STRUCTURE_RE.match(line)
        if m:
            indent = len(m.group(1))
            kind = m.group(2)
            name = m.group(3)
            symbols.append({
                "line": i,
                "kind": kind,
                "name": name,
                "indent": indent,
                "text": line.rstrip(),
            })
            if len(symbols) >= max_symbols:
                break
    return symbols


def _extract_md_structure(lines: list[str]) -> list[dict[str, Any]]:
    """Extract heading-based landmarks from markdown."""

    landmarks: list[dict[str, Any]] = []
    for i, line in enumerate(lines, 1):
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            landmarks.append({"line": i, "level": level, "text": text})
    return landmarks


def _extract_text_landmarks(
    lines: list[str],
    max_landmarks: int = 12,
) -> list[dict[str, Any]]:
    """Extract evenly-spaced landmarks from plain text/log files."""

    total = len(lines)
    if total == 0:
        return []

    landmarks: list[dict[str, Any]] = []
    landmarks.append({"line": 1, "text": lines[0].rstrip()[:80]})

    if total > 2:
        step = max(1, total // max_landmarks)
        for i in range(step, total - 1, step):
            text = lines[i].rstrip()[:80]
            if text.strip():
                landmarks.append({"line": i + 1, "text": text})
            if len(landmarks) >= max_landmarks - 1:
                break

    if total > 1:
        landmarks.append({"line": total, "text": lines[-1].rstrip()[:80]})

    return landmarks


# ── Presentation functions ───────────────────────────────────────────


def present_read_slice(
    path: str,
    content: str,
    start_line: int,
    end_line: int,
    total_lines: int,
    size_bytes: int,
) -> str:
    """Present a file read with metadata header and footer.

    Every read response now tells the model where it is in the file,
    how much is left, and gives it anchors for the next step.
    """

    size_human = _human_size(size_bytes)
    header = f"── {path} ({total_lines} lines, {size_human}) [{start_line}:{end_line}] ──"

    remaining = total_lines - end_line
    if remaining > 0:
        footer = (
            f"── showing {start_line}-{end_line} of {total_lines}"
            f" | {remaining} lines remaining ──"
        )
    else:
        footer = f"── showing {start_line}-{end_line} of {total_lines} ──"

    return f"{header}\n{content}\n{footer}"


def present_file_map(
    path: str,
    head_lines: list[str],
    total_lines: int,
    size_bytes: int,
    tail_lines: list[str] | None = None,
    tail_start_line: int = 0,
    head_count: int = 30,
    tail_count: int = 15,
) -> str:
    """Present a structural map for a large code file.

    Returns structure + head + tail + next-step anchors.
    This replaces the dead-end refusal that used to block the model.
    """

    size_human = _human_size(size_bytes)
    parts = [f"── {path} ({total_lines} lines, {size_human}) ──"]

    # Structure
    symbols = _extract_code_structure(head_lines)
    if symbols:
        parts.append("\n[structure]")
        for s in symbols:
            pad = " " * (s["indent"] // 2)
            label = f"{pad}{s['kind']} {s['name']}"
            parts.append(f"  {label:<42} L{s['line']}")

    # Head
    head_end = min(head_count, len(head_lines), total_lines)
    if head_end > 0:
        parts.append(f"\n[head: 1-{head_end}]")
        parts.append("\n".join(head_lines[:head_end]))

    # Tail
    if tail_lines and tail_start_line > 0:
        parts.append(f"\n[tail: {tail_start_line}-{total_lines}]")
        parts.append("\n".join(tail_lines))
    elif len(head_lines) >= total_lines and total_lines > head_count + tail_count:
        ts = total_lines - tail_count
        parts.append(f"\n[tail: {ts + 1}-{total_lines}]")
        parts.append("\n".join(head_lines[ts:]))

    # Next targets
    parts.append("\n[next targets]")
    if symbols:
        for s in symbols[:3]:
            end = min(s["line"] + 60, total_lines)
            parts.append(f"  • open {path} {s['line']}-{end}")
    else:
        mid = total_lines // 2
        parts.append(f"  • open {path} {mid}-{min(mid + 80, total_lines)}")
    parts.append(f"  • locate \"<keyword>\" {path}")

    return "\n".join(parts)


def present_segmented_outline(
    path: str,
    head_lines: list[str],
    total_lines: int,
    size_bytes: int,
    head_count: int = 20,
) -> str:
    """Present a segmented outline for markdown/text/log files."""

    size_human = _human_size(size_bytes)
    parts = [f"── {path} ({total_lines} lines, {size_human}) ──"]

    ext = os.path.splitext(path)[1].lower()

    if ext in (".md", ".markdown", ".rst"):
        landmarks = _extract_md_structure(head_lines)
        if landmarks:
            parts.append("\n[landmarks]")
            for lm in landmarks:
                indent = "  " * (lm["level"] - 1)
                parts.append(
                    f"  L{lm['line']:<6} {indent}{'#' * lm['level']} {lm['text']}"
                )
    else:
        landmarks = _extract_text_landmarks(head_lines)
        if landmarks:
            parts.append("\n[landmarks]")
            for lm in landmarks:
                parts.append(f"  L{lm['line']:<6} {lm['text']}")

    # Head
    head_end = min(head_count, len(head_lines), total_lines)
    if head_end > 0:
        parts.append(f"\n[head: 1-{head_end}]")
        parts.append("\n".join(head_lines[:head_end]))

    # Next targets
    if landmarks and len(landmarks) > 1:
        parts.append("\n[next targets]")
        for lm in landmarks[1:4]:
            end_l = min(lm["line"] + 60, total_lines)
            parts.append(f"  • open {path} {lm['line']}-{end_l}")
        parts.append(f'  • locate "<keyword>" {path}')

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
    """Auto-select the best preview for a large file.

    This is the core replacement for the dead-end refusal.
    Instead of blocking the model, it returns a navigable map.
    """

    if kind != "text" or not head_lines:
        return f"[{kind} file: {mime}, {_human_size(size_bytes)}]"

    ext = os.path.splitext(path)[1].lower()

    if ext in _CODE_EXTENSIONS:
        return present_file_map(
            path, head_lines, total_lines, size_bytes,
            tail_lines=tail_lines, tail_start_line=tail_start_line,
        )

    if ext in _TEXT_EXTENSIONS:
        return present_segmented_outline(
            path, head_lines, total_lines, size_bytes,
        )

    # Unknown extension — try code structure, fall back to outline
    symbols = _extract_code_structure(head_lines, max_symbols=3)
    if symbols:
        return present_file_map(
            path, head_lines, total_lines, size_bytes,
            tail_lines=tail_lines, tail_start_line=tail_start_line,
        )
    return present_segmented_outline(
        path, head_lines, total_lines, size_bytes,
    )


def present_grep_results(
    matches: list[dict[str, Any]],
    pattern: str,
    path: str,
    cluster_threshold: int = GREP_CLUSTER_THRESHOLD,
) -> str:
    """Present grep results — flat for small sets, clustered for large."""

    if not matches:
        return "(no matches)"

    total = len(matches)

    # Below threshold → flat with header
    if total <= cluster_threshold:
        lines = [f"── grep: \"{pattern}\" in {path} ── {total} matches"]
        for m in matches:
            lines.append(f"{m['path']}:{m['line_number']}:{m['line']}")
        return "\n".join(lines)

    # Above threshold → clustered
    file_groups: dict[str, list[dict[str, Any]]] = {}
    for m in matches:
        file_groups.setdefault(m["path"], []).append(m)

    sorted_files = sorted(
        file_groups.items(), key=lambda x: len(x[1]), reverse=True,
    )

    parts = [
        f"── grep: \"{pattern}\" in {path}"
        f" ── {total} matches in {len(sorted_files)} files"
    ]

    # Densest files
    parts.append("\n[densest files]")
    for fpath, fmatches in sorted_files[:8]:
        parts.append(f"  {fpath:<45} ({len(fmatches)} hits)")
    if len(sorted_files) > 8:
        parts.append(f"  ... and {len(sorted_files) - 8} more files")

    # Representative matches
    parts.append("\n[representative matches]")
    shown = 0
    for fpath, fmatches in sorted_files[:5]:
        for m in fmatches[:3]:
            parts.append(f"  {m['path']}:{m['line_number']}:{m['line']}")
            shown += 1
            if shown >= 15:
                break
        if shown >= 15:
            break

    # Next targets
    parts.append("\n[next targets]")
    for fpath, fmatches in sorted_files[:3]:
        first = fmatches[0]
        start = max(1, first["line_number"] - 5)
        end = first["line_number"] + 30
        parts.append(f"  • open {fpath} {start}-{end}")

    return "\n".join(parts)


# ── Helpers ──────────────────────────────────────────────────────────


def _human_size(size_bytes: int) -> str:
    """Convert bytes to human-readable size."""

    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"
