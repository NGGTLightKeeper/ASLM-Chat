# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Render deep-research source dump JSONL into a readable Markdown report.

Usage:
    python scripts/render_source_dump.py logs/deep_research/source_dumps/run.jsonl
    python scripts/render_source_dump.py logs/deep_research/source_dumps/run.jsonl --out report.md
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python scripts/render_source_dump.py",
        description="Render a deep-research source dump JSONL into readable Markdown.",
    )
    parser.add_argument("jsonl", type=Path, help="Path to source dump JSONL")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Markdown output path. Defaults to <jsonl stem>.readable.md next to the JSONL.",
    )
    parser.add_argument(
        "--include-full-text",
        action="store_true",
        help="Include full parsed source text after relevant_chunks. This can make the report large.",
    )
    parser.add_argument(
        "--max-text-chars",
        type=int,
        default=12_000,
        help="Per-source cap for full text when --include-full-text is set.",
    )
    parser.add_argument(
        "--max-chunks-chars",
        type=int,
        default=8_000,
        help="Per-source cap for relevant_chunks.",
    )
    parser.add_argument(
        "--max-entities",
        type=int,
        default=32,
        help="Max GLiNER entities to show per source.",
    )
    return parser.parse_args()


def _load_records(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    meta: dict[str, Any] = {}

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
            if record_type == "source":
                sources.append(record)
            elif record_type == "snapshot":
                snapshots.append(record)
            elif record_type in {"run_start", "run_end"}:
                meta[record_type] = record

    return sources, snapshots, meta


def _one_line(text: str, limit: int = 140) -> str:
    value = " ".join((text or "").split())
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _truncate(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    head = text[:max_chars].rstrip()
    return head + f"\n\n[...truncated {len(text) - len(head)} chars]"


def _dedupe_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for entity in entities:
        text = str(entity.get("text", "")).strip()
        label = str(entity.get("label", "")).strip()
        if not text or not label:
            continue
        key = (text.lower(), label.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(entity)
    return out


def _source_metrics(source: dict[str, Any]) -> dict[str, Any]:
    text = source.get("text", "") or ""
    chunks = source.get("relevant_chunks", "") or ""
    text_chars = int(source.get("text_chars") or len(text))
    chunk_chars = int(source.get("relevant_chunks_chars") or len(chunks))
    if "relevant_chunks_is_densified" in source:
        densified = bool(source.get("relevant_chunks_is_densified"))
    else:
        densified = bool(chunks) and chunks != text
    ratio = source.get("relevant_chunks_compression_ratio")
    if ratio is None:
        ratio = round(chunk_chars / text_chars, 4) if text_chars and chunk_chars else 0.0
    return {
        "text_chars": text_chars,
        "chunk_chars": chunk_chars,
        "densified": densified,
        "ratio": float(ratio or 0.0),
    }


def _render_entities(entities: list[dict[str, Any]], max_entities: int) -> str:
    entities = _dedupe_entities(entities)[:max_entities]
    if not entities:
        return "_No GLiNER entities recorded._"
    parts = []
    for entity in entities:
        text = str(entity.get("text", "")).strip()
        label = str(entity.get("label", "")).strip()
        score = entity.get("score")
        suffix = f" ({score})" if score not in (None, "") else ""
        parts.append(f"`{text}`:{label}{suffix}")
    return ", ".join(parts)


def _slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return value or "source"


def render_markdown(
    *,
    jsonl_path: Path,
    sources: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    meta: dict[str, Any],
    include_full_text: bool,
    max_text_chars: int,
    max_chunks_chars: int,
    max_entities: int,
) -> str:
    run_start = meta.get("run_start", {})
    run_end = meta.get("run_end", {})
    title = f"Source Dump: {jsonl_path.name}"

    densified_count = sum(1 for source in sources if _source_metrics(source)["densified"])
    full_count = sum(1 for source in sources if not _source_metrics(source)["densified"])
    entities_count = sum(1 for source in sources if source.get("entities"))

    lines: list[str] = [
        f"# {title}",
        "",
        f"- Question: {run_start.get('question', '-')}",
        f"- Depth: {run_start.get('depth', '-')}",
        f"- Created: {run_start.get('created_at', '-')}",
        f"- Sources: {len(sources)}",
        f"- Densified sources: {densified_count}",
        f"- Full-text sources: {full_count}",
        f"- Sources with entities: {entities_count}",
    ]
    if run_end:
        lines.extend([
            f"- Status: {run_end.get('status', '-')}",
            f"- Snapshots: {run_end.get('snapshots', '-')}",
            f"- Sources written: {run_end.get('sources_written', '-')}",
        ])

    if snapshots:
        lines.extend(["", "## Snapshots", ""])
        lines.append("| Snapshot | Phase | Sources | Raw Results | Elapsed |")
        lines.append("| ---: | --- | ---: | ---: | ---: |")
        for snapshot in snapshots:
            lines.append(
                "| "
                f"{snapshot.get('snapshot_id', '')} | "
                f"{snapshot.get('phase', '')} | "
                f"{snapshot.get('sources_after_filter', '')} | "
                f"{snapshot.get('raw_results_seen', '')} | "
                f"{snapshot.get('elapsed_sec', '')}s |"
            )

    lines.extend(["", "## Sources", ""])
    lines.append("| # | Snapshot | Mode | Ratio | Text | Chunks | Entities | Title |")
    lines.append("| ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |")
    for index, source in enumerate(sources, 1):
        metrics = _source_metrics(source)
        mode = "densified" if metrics["densified"] else "full"
        title_cell = _one_line(source.get("title", "") or source.get("url", ""), 90).replace("|", "\\|")
        lines.append(
            "| "
            f"{index} | "
            f"{source.get('snapshot_id', '')} | "
            f"{mode} | "
            f"{metrics['ratio']:.3f} | "
            f"{metrics['text_chars']} | "
            f"{metrics['chunk_chars']} | "
            f"{len(source.get('entities') or [])} | "
            f"{title_cell} |"
        )

    for index, source in enumerate(sources, 1):
        metrics = _source_metrics(source)
        mode = "densified" if metrics["densified"] else "full text"
        title = source.get("title", "") or source.get("url", "") or f"Source {index}"
        anchor = _slug(f"{index}-{title}")
        lines.extend([
            "",
            f"## {index}. {title}",
            "",
            f"<a id=\"{anchor}\"></a>",
            "",
            f"- URL: {source.get('url', '-')}",
            f"- Snapshot: {source.get('snapshot_id', '-')} / {source.get('phase', '-')}",
            f"- Mode: {mode}",
            f"- Relevance: {float(source.get('relevance_score', 0.0) or 0.0):.4f}",
            f"- Text chars: {metrics['text_chars']}",
            f"- Relevant chunks chars: {metrics['chunk_chars']}",
            f"- Compression ratio: {metrics['ratio']:.4f}",
            f"- Extraction method: {source.get('extraction_method', '-')}",
            "",
            "### GLiNER Entities",
            "",
            _render_entities(source.get("entities") or [], max_entities),
            "",
            "### Relevant Chunks",
            "",
            "```text",
            _truncate(source.get("relevant_chunks", "") or "", max_chunks_chars),
            "```",
        ])
        if include_full_text:
            lines.extend([
                "",
                "### Full Parsed Text",
                "",
                "```text",
                _truncate(source.get("text", "") or "", max_text_chars),
                "```",
            ])

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    args = _parse_args()
    jsonl_path = args.jsonl
    if not jsonl_path.exists():
        raise SystemExit(f"JSONL not found: {jsonl_path}")
    sources, snapshots, meta = _load_records(jsonl_path)
    out_path = args.out or jsonl_path.with_name(f"{jsonl_path.stem}.readable.md")
    markdown = render_markdown(
        jsonl_path=jsonl_path,
        sources=sources,
        snapshots=snapshots,
        meta=meta,
        include_full_text=bool(args.include_full_text),
        max_text_chars=max(0, int(args.max_text_chars)),
        max_chunks_chars=max(0, int(args.max_chunks_chars)),
        max_entities=max(0, int(args.max_entities)),
    )
    out_path.write_text(markdown, encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
