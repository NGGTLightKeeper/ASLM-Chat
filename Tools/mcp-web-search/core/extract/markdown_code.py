# Copyright NEXTGGTECH. Elastic License 2.0.

"""Protect HTML ``<pre>`` blocks while generic extractors process surrounding prose."""

from __future__ import annotations

import hashlib
import re
from copy import copy


_LANGUAGE_RE = re.compile(r"^(?:language|lang)-([A-Za-z0-9_.+-]+)$", re.IGNORECASE)
_SAFE_LANGUAGE_RE = re.compile(r"^[A-Za-z0-9_.+-]+$")
_FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


# Return a Markdown fence marker from one line, or an empty string.
def markdown_fence_marker(line: str) -> str:
    match = _FENCE_RE.match(line or "")
    return match.group(1) if match else ""


# True only for a valid closing fence (no info string after the delimiter).
def closes_markdown_fence(line: str, marker: str) -> bool:
    stripped = (line or "").strip()
    if not marker or not stripped.startswith(marker[0] * len(marker)):
        return False
    return not stripped[len(marker):].strip(marker[0]).strip()


# Extract preformatted text without flattening indentation or React-style div.cm-line rows.
def pre_to_text(pre) -> str:
    from bs4 import NavigableString

    clone = copy(pre)

    for br in clone.find_all("br"):
        br.replace_with("\n")
    for container in (clone, *clone.find_all("code")):
        if container.find("div", recursive=False):
            for child in list(container.children):
                if isinstance(child, NavigableString) and not str(child).strip():
                    child.extract()
    for div in reversed(clone.find_all("div")):
        if not div.get_text("", strip=False).endswith("\n"):
            div.append("\n")

    lines = clone.get_text("", strip=False).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


# Infer a fence info string from structural attributes only.
def _language(pre) -> str:
    code = pre.find("code")
    nodes = (code, pre) if code is not None else (pre,)
    for node in nodes:
        explicit = node.get("data-language") or node.get("data-lang")
        if explicit and _SAFE_LANGUAGE_RE.fullmatch(str(explicit)):
            return str(explicit)
        for token in node.get("class") or ():
            match = _LANGUAGE_RE.fullmatch(str(token))
            if match:
                return match.group(1)

    # Sandpack/CodeMirror markup used by React docs exposes the language as the last
    # ``sp-*`` class on <pre>; choosing the last structural token avoids host rules.
    sandpack = [str(token)[3:] for token in pre.get("class") or () if str(token).startswith("sp-")]
    if sandpack and _SAFE_LANGUAGE_RE.fullmatch(sandpack[-1]):
        return sandpack[-1]
    return ""


# Wrap code in a fence longer than every backtick run contained in the code itself.
def fenced_code(text: str, language: str = "") -> str:
    longest = max((len(run) for run in re.findall(r"`+", text or "")), default=0)
    fence = "`" * max(3, longest + 1)
    info = language if _SAFE_LANGUAGE_RE.fullmatch(language or "") else ""
    return f"{fence}{info}\n{text}\n{fence}"


# Wrap every <pre> with boundary markers while leaving the original DOM intact.
def wrap_pre_with_markers(soup) -> list[tuple[str, str, str]]:
    source_fingerprint = hashlib.sha256(str(soup).encode("utf-8", errors="replace")).hexdigest()[:24].upper()
    markers: list[tuple[str, str, str]] = []
    for index, pre in enumerate(list(soup.find_all("pre"))):
        text = pre_to_text(pre)
        language = _language(pre)
        if not text:
            continue
        start = f"ASLMCODESTART{source_fingerprint}{index:04d}END"
        stop = f"ASLMCODESTOP{source_fingerprint}{index:04d}END"
        start_node = soup.new_tag("p")
        stop_node = soup.new_tag("p")
        start_node.string = start
        stop_node.string = stop
        pre.insert_before(start_node)
        pre.insert_after(stop_node)
        markers.append((start, stop, fenced_code(text, language)))
    return markers


# Replace each extracted START..STOP range with exact fenced Markdown.
def restore_pre_markers(text: str, markers: list[tuple[str, str, str]]) -> str:
    restored = text or ""
    for start, stop, markdown in markers:
        start_position = restored.find(start)
        stop_position = restored.find(stop, start_position + len(start)) if start_position >= 0 else -1
        if start_position >= 0 and stop_position >= 0:
            before = restored[:start_position]
            after = restored[stop_position + len(stop):]
            replacement = markdown
            if before and not before.endswith("\n"):
                replacement = "\n" + replacement
            if after and not after.startswith("\n"):
                replacement += "\n"
            restored = before + replacement + after
        else:
            # Never expose internal markers when an extractor keeps only one boundary.
            restored = restored.replace(start, "").replace(stop, "")
    return restored


# Collapse excessive prose whitespace without modifying blank lines inside code fences.
def collapse_blank_lines_preserving_fences(markdown: str) -> str:
    lines = (markdown or "").split("\n")
    output: list[str] = []
    marker = ""
    blank_run = 0
    for line in lines:
        current = markdown_fence_marker(line)
        if marker:
            if closes_markdown_fence(line, marker):
                marker = ""
            output.append(line)
            blank_run = 0
            continue
        if current:
            marker = current
            output.append(line)
            blank_run = 0
            continue

        if line.strip():
            output.append(line)
            blank_run = 0
        else:
            blank_run += 1
            if blank_run <= 2:
                output.append(line)
    return "\n".join(output)
