# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""GFM table helpers — render <table> to markdown, and repair markdown tables.

Two jobs, both dependency-light (bs4 + string ops, no new HTML→markdown library):

  1. `html_table_to_markdown` — turn one <table> node into a GitHub-flavoured markdown
     table, with header promotion (a table with no <th> gets its first row as the header)
     and empty-row skipping. Used by the full-body / data-island rescue paths, which
     otherwise flatten a table to a wall of `get_text()` and lose the column structure.

  2. `normalize_markdown_tables` — repair table blocks already in markdown. trafilatura's
     formatted output emits real tables but drops the leading `|` on the header row and can
     omit the separator; this restores both and drops all-blank rows, so every renderer
     parses the table. Prose lines that merely contain `|` are left untouched — a table
     block is only recognised by its dashed separator row.

These mirror the intent of openserp's html-to-markdown table plugin (skip-empty-rows +
header-promotion) without porting the whole Go converter, since trafilatura already renders
tables on the main path.
"""

from __future__ import annotations

import re

_SEP_LINE_RE = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")


# Escape a cell so its content can't break the markdown table grid.
def _cell(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).replace("|", "\\|").strip()


# Render one bs4 <table> node to a GFM markdown table, or "" when it has no usable rows.
def html_table_to_markdown(table) -> str:
    rows: list[list[str]] = []
    header_from_th = False
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        values = [_cell(c.get_text(separator=" ", strip=True)) for c in cells]
        if not any(values):  # skip fully-blank rows
            continue
        if not rows and any(c.name == "th" for c in cells):
            header_from_th = True
        rows.append(values)
    if not rows:
        return ""

    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]

    # Header promotion: a <th>-less table still gets a header — its first row (matches
    # openserp's WithHeaderPromotion). Either way the header is row 0.
    header = rows[0]
    body = rows[1:]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for r in body:
        lines.append("| " + " | ".join(r) + " |")
    _ = header_from_th  # both header sources land in row 0; kept for clarity/debugging
    return "\n".join(lines)


# Replace every <table> in a bs4 tree with a positional marker, returning (tree-mutated,
# {marker: markdown}). The caller substitutes markers back after get_text(), so tables keep
# their place in the surrounding text instead of collapsing into it.
def swap_tables_for_markers(soup, tag_prefix: str = "\x00TBL") -> dict[str, str]:
    markers: dict[str, str] = {}
    for i, table in enumerate(soup.find_all("table")):
        md = html_table_to_markdown(table)
        marker = f"{tag_prefix}{i}\x00"
        markers[marker] = md
        table.replace_with(marker if md else "")
    return markers


# One markdown table block (list of raw lines) → repaired GFM lines. Ensures a leading and
# trailing `|` on every row, inserts a separator after the header when missing, and drops
# all-blank rows.
def _repair_table_block(block: list[str]) -> list[str]:
    def cells(line: str) -> list[str]:
        s = line.strip()
        s = s.removeprefix("|").removesuffix("|")
        return [c.strip() for c in s.split("|")]

    data_rows: list[list[str]] = []
    has_sep = False
    for line in block:
        if _SEP_LINE_RE.match(line):
            has_sep = True
            continue
        row = cells(line)
        if any(row):
            data_rows.append(row)
    if not data_rows:
        return block  # nothing recognisable — leave as-is

    width = max(len(r) for r in data_rows)
    data_rows = [r + [""] * (width - len(r)) for r in data_rows]
    out = ["| " + " | ".join(data_rows[0]) + " |"]
    out.append("| " + " | ".join(["---"] * width) + " |")
    for r in data_rows[1:]:
        out.append("| " + " | ".join(r) + " |")
    _ = has_sep
    return out


# Repair every markdown table in a document. A table block is a run of ≥2 consecutive
# non-blank lines that all contain `|` AND include a dashed separator row — so prose lines
# with an incidental pipe are never touched.
def normalize_markdown_tables(markdown: str) -> str:
    if "|" not in (markdown or ""):
        return markdown
    lines = markdown.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        # Gather a maximal run of consecutive pipe-bearing non-blank lines.
        j = i
        while j < n and lines[j].strip() and "|" in lines[j]:
            j += 1
        run = lines[i:j]
        if len(run) >= 2 and any(_SEP_LINE_RE.match(ln) for ln in run):
            out.extend(_repair_table_block(run))
            i = j
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)
