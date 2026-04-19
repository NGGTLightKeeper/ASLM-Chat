# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Render the source content shape that final synthesis sees.

Usage:
    python scripts/render_synthesis_preview.py logs/deep_research/source_dumps/run.jsonl
    python scripts/render_synthesis_preview.py logs/deep_research/source_dumps/run.jsonl --out preview.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.deep_research.text_utils import sanitize_content as _sanitize_content

from services.deep_research.config import SYNTH_CHAR_BUDGET_PER_SOURCE


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python scripts/render_synthesis_preview.py",
        description="Render Markdown with the exact per-source blocks used by synthesis.",
    )
    parser.add_argument("jsonl", type=Path, help="Path to source dump JSONL")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Markdown output path. Defaults to <jsonl stem>.synthesis_preview.md.",
    )
    parser.add_argument(
        "--per-source-budget",
        type=int,
        default=SYNTH_CHAR_BUDGET_PER_SOURCE,
        help="Character budget per source block, matching synthesis default unless overridden.",
    )
    return parser.parse_args()


def _load_sources(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    run_start: dict[str, Any] = {}
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid JSON at {path}:{line_no}: {exc}") from exc
            record_type = record.get("record_type")
            if record_type == "run_start":
                run_start = record
            elif record_type == "source":
                sources.append(record)
    return sources, run_start


def _pick_synthesis_content(source: dict[str, Any]) -> tuple[str, str]:
    for field in ("summary", "relevant_chunks", "text"):
        value = _sanitize_content(str(source.get(field, "") or ""))
        if value:
            return field, value
    return "empty", ""


def _build_source_block(
    source: dict[str, Any],
    index: int,
    per_source_budget: int,
) -> tuple[str, str, int, int]:
    chosen_field, content = _pick_synthesis_content(source)
    original_content_chars = len(content)
    header = (
        f"\n[SOURCE {index}]\n"
        f"Title: {source.get('title', '')}\n"
        f"URL: {source.get('url', '')}\n"
    )
    if source.get("sub_topic"):
        header += f"Sub-topic: {source.get('sub_topic')}\n"
    if source.get("content_type"):
        header += f"Type: {source.get('content_type')}\n"
    header += "Content:\n"
    max_content_chars = max(500, per_source_budget - len(header) - 10)
    if len(content) > max_content_chars:
        content = content[:max_content_chars].rstrip()
    block = f"{header}{content}\n"
    return chosen_field, block, original_content_chars, len(content)


def _one_line(text: str, limit: int = 120) -> str:
    value = " ".join((text or "").split())
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0 or numerator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _field_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"summary": 0, "relevant_chunks": 0, "text": 0, "empty": 0}
    for row in rows:
        counts[str(row["chosen_field"])] = counts.get(str(row["chosen_field"]), 0) + 1
    return counts


def render_markdown(
    *,
    jsonl_path: Path,
    sources: list[dict[str, Any]],
    run_start: dict[str, Any],
    per_source_budget: int,
) -> tuple[str, dict[str, int]]:
    rows: list[dict[str, Any]] = []
    for index, source in enumerate(sources, 1):
        chosen_field, block, chosen_chars_before_cap, chosen_chars_after_cap = _build_source_block(
            source,
            index,
            per_source_budget,
        )
        text_chars = int(source.get("text_chars") or len(str(source.get("text", "") or "")))
        chunks_chars = int(
            source.get("relevant_chunks_chars")
            or len(str(source.get("relevant_chunks", "") or ""))
        )
        rows.append(
            {
                "index": index,
                "source": source,
                "chosen_field": chosen_field,
                "block": block,
                "text_chars": text_chars,
                "chunks_chars": chunks_chars,
                "chosen_chars_before_cap": chosen_chars_before_cap,
                "chosen_chars_after_cap": chosen_chars_after_cap,
            }
        )

    counts = _field_counts(rows)
    densified = sum(
        1
        for row in rows
        if row["chunks_chars"] > 0 and row["text_chars"] > 0 and row["chunks_chars"] < row["text_chars"]
    )
    capped = sum(
        1
        for row in rows
        if int(row["chosen_chars_after_cap"]) < int(row["chosen_chars_before_cap"])
    )

    lines: list[str] = [
        f"# Synthesis Preview: {jsonl_path.name}",
        "",
        f"- Question: {run_start.get('question', '-')}",
        f"- Depth: {run_start.get('depth', '-')}",
        f"- Sources: {len(rows)}",
        f"- Per-source block budget: {per_source_budget}",
        f"- Chosen from summary: {counts.get('summary', 0)}",
        f"- Chosen from relevant_chunks: {counts.get('relevant_chunks', 0)}",
        f"- Chosen from text fallback: {counts.get('text', 0)}",
        f"- Empty content: {counts.get('empty', 0)}",
        f"- Densified relevant_chunks: {densified}",
        f"- Blocks capped by synthesis budget: {capped}",
        "",
        "This preview uses the same field priority as synthesis: `summary or relevant_chunks or text`.",
        "",
        "## Source Table",
        "",
        "| # | Picked | Text | Chunks | Ratio | Picked Before Cap | Picked In Block | Title |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]

    for row in rows:
        source = row["source"]
        title = _one_line(str(source.get("title", "") or source.get("url", "")), 90).replace("|", "\\|")
        lines.append(
            "| "
            f"{row['index']} | "
            f"{row['chosen_field']} | "
            f"{row['text_chars']} | "
            f"{row['chunks_chars']} | "
            f"{_ratio(int(row['chunks_chars']), int(row['text_chars'])):.3f} | "
            f"{row['chosen_chars_before_cap']} | "
            f"{row['chosen_chars_after_cap']} | "
            f"{title} |"
        )

    for row in rows:
        source = row["source"]
        lines.extend(
            [
                "",
                f"## {row['index']}. {source.get('title', '') or source.get('url', '')}",
                "",
                f"- URL: {source.get('url', '-')}",
                f"- Picked field: {row['chosen_field']}",
                f"- Text chars: {row['text_chars']}",
                f"- Relevant chunks chars: {row['chunks_chars']}",
                f"- Relevant chunks/text ratio: {_ratio(int(row['chunks_chars']), int(row['text_chars'])):.4f}",
                f"- Picked chars before synthesis cap: {row['chosen_chars_before_cap']}",
                f"- Picked chars inside block: {row['chosen_chars_after_cap']}",
                "",
                "### Synthesis Block",
                "",
                "```text",
                str(row["block"]).rstrip(),
                "```",
            ]
        )

    return "\n".join(lines).rstrip() + "\n", counts


def main() -> None:
    args = _parse_args()
    jsonl_path = args.jsonl
    if not jsonl_path.exists():
        raise SystemExit(f"JSONL not found: {jsonl_path}")
    sources, run_start = _load_sources(jsonl_path)
    out_path = args.out or jsonl_path.with_name(f"{jsonl_path.stem}.synthesis_preview.md")
    markdown, counts = render_markdown(
        jsonl_path=jsonl_path,
        sources=sources,
        run_start=run_start,
        per_source_budget=max(500, int(args.per_source_budget)),
    )
    out_path.write_text(markdown, encoding="utf-8")
    print(out_path)
    print(
        "sources={sources} summary={summary} relevant_chunks={chunks} text={text} empty={empty}".format(
            sources=len(sources),
            summary=counts.get("summary", 0),
            chunks=counts.get("relevant_chunks", 0),
            text=counts.get("text", 0),
            empty=counts.get("empty", 0),
        )
    )


if __name__ == "__main__":
    main()
