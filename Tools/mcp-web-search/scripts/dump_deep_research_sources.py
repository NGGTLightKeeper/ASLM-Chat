# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Run deep-research source collection and dump filtered sources.

This is a diagnostic runner. It does not change the pipeline modules; instead it
wraps run_dedup_filter inside this process and writes every source that survives
semantic deduplication and the GLiNER density filter to a JSONL file.

Usage:
    python scripts/dump_deep_research_sources.py "what is gliner" --depth extra
    python scripts/dump_deep_research_sources.py "what is gliner" --depth extra --with-synthesis
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


DEFAULT_DUMP_DIR = REPO_ROOT / "logs" / "deep_research" / "source_dumps"


class FilteredSourceDumper:
    """Append filtered source snapshots to a JSONL file during a research run."""

    def __init__(
        self,
        *,
        path: Path,
        question: str,
        depth: str,
        unique_only: bool,
    ) -> None:
        self.path = path
        self.question = question
        self.depth = depth
        self.unique_only = unique_only
        self.snapshot_count = 0
        self.sources_written = 0
        self._seen_keys: set[str] = set()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write(
            {
                "record_type": "run_start",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "question": question,
                "depth": depth,
                "unique_only": unique_only,
            }
        )

    def dump_snapshot(self, state: Any, *, phase_label: str) -> None:
        self.snapshot_count += 1
        snapshot_id = self.snapshot_count
        total_sources = len(getattr(state, "extracted_sources", []) or [])
        self._write(
            {
                "record_type": "snapshot",
                "snapshot_id": snapshot_id,
                "phase": phase_label,
                "elapsed_sec": round(float(getattr(state, "elapsed", 0.0) or 0.0), 2),
                "sources_after_filter": total_sources,
                "raw_results_seen": len(getattr(state, "raw_results", []) or []),
                "attempted_followups": list(getattr(state, "attempted_followups", []) or []),
            }
        )

        written_this_snapshot = 0
        for source_index, source in enumerate(getattr(state, "extracted_sources", []) or [], 1):
            key = self._source_key(source)
            if self.unique_only and key in self._seen_keys:
                continue
            self._seen_keys.add(key)
            self._write(
                self._source_record(
                    state=state,
                    source=source,
                    snapshot_id=snapshot_id,
                    source_index=source_index,
                    total_sources=total_sources,
                    phase_label=phase_label,
                )
            )
            self.sources_written += 1
            written_this_snapshot += 1

        state.log(
            "  Filtered-source dump: "
            f"snapshot={snapshot_id} wrote={written_this_snapshot} "
            f"total_written={self.sources_written} path={self.path}"
        )

    def finish(self, *, status: str, errors: list[str] | None = None) -> None:
        self._write(
            {
                "record_type": "run_end",
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "status": status,
                "snapshots": self.snapshot_count,
                "sources_written": self.sources_written,
                "errors": errors or [],
            }
        )

    def _source_record(
        self,
        *,
        state: Any,
        source: Any,
        snapshot_id: int,
        source_index: int,
        total_sources: int,
        phase_label: str,
    ) -> dict[str, Any]:
        text = getattr(source, "text", "") or ""
        relevant_chunks = getattr(source, "relevant_chunks", "") or ""
        entities = getattr(source, "entities", []) or []
        text_chars = len(text)
        relevant_chars = len(relevant_chunks)
        is_densified = bool(relevant_chunks) and relevant_chunks != text
        compression_ratio = (
            round(relevant_chars / text_chars, 4)
            if text_chars > 0 and relevant_chars > 0
            else 0.0
        )
        return {
            "record_type": "source",
            "snapshot_id": snapshot_id,
            "phase": phase_label,
            "source_index": source_index,
            "sources_in_snapshot": total_sources,
            "elapsed_sec": round(float(getattr(state, "elapsed", 0.0) or 0.0), 2),
            "question": self.question,
            "depth": self.depth,
            "title": getattr(source, "title", ""),
            "url": getattr(source, "url", ""),
            "relevance_score": float(getattr(source, "relevance_score", 0.0) or 0.0),
            "char_count": int(getattr(source, "char_count", 0) or 0),
            "extraction_method": getattr(source, "extraction_method", ""),
            "content_hash": getattr(source, "content_hash", ""),
            "text_chars": text_chars,
            "relevant_chunks_chars": relevant_chars,
            "relevant_chunks_is_full_text": bool(relevant_chunks) and relevant_chunks == text,
            "relevant_chunks_is_densified": is_densified,
            "relevant_chunks_compression_ratio": compression_ratio,
            "entities_count": len(entities),
            "sub_topic": getattr(source, "sub_topic", ""),
            "content_type": getattr(source, "content_type", ""),
            "evidence_strength": getattr(source, "evidence_strength", ""),
            "source_character": getattr(source, "source_character", ""),
            "perspective": getattr(source, "perspective", ""),
            "entities": entities,
            "relevant_chunks": relevant_chunks,
            "summary": getattr(source, "summary", ""),
            "text": text,
        }

    def _source_key(self, source: Any) -> str:
        content_hash = str(getattr(source, "content_hash", "") or "").strip()
        if content_hash:
            return f"hash:{content_hash}"
        url = str(getattr(source, "url", "") or "").strip().lower().rstrip("/")
        if url:
            return f"url:{url}"
        title = str(getattr(source, "title", "") or "").strip().lower()
        return f"title:{title}"

    def _write(self, record: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False)
            handle.write("\n")


def _default_dump_path(depth: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return DEFAULT_DUMP_DIR / f"{timestamp}_{depth}_filtered_sources.jsonl"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python scripts/dump_deep_research_sources.py",
        description="Run deep research and dump sources after semantic+GLiNER filtering.",
    )
    parser.add_argument("question", help="Research question")
    parser.add_argument(
        "--depth",
        choices=["low", "medium", "high", "extra"],
        default="extra",
        help="Research depth. Use high/extra if you want GLiNER filtering.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="JSONL dump path. Defaults to logs/deep_research/source_dumps/<timestamp>_<depth>_filtered_sources.jsonl",
    )
    parser.add_argument(
        "--include-duplicates",
        action="store_true",
        help="Write the same retained source again on later filter snapshots.",
    )
    parser.add_argument(
        "--with-synthesis",
        action="store_true",
        help="Also run the final synthesis phase. By default only source collection is run.",
    )
    parser.add_argument("--max-iterations", type=int, default=None, help="Override depth preset max_iterations")
    parser.add_argument("--max-sources", type=int, default=None, help="Override depth preset max_sources")
    parser.add_argument(
        "--max-results-per-query",
        type=int,
        default=None,
        help="Override depth preset max_results_per_query",
    )
    parser.add_argument(
        "--extract-limit",
        type=int,
        default=None,
        help="Override depth preset max_urls_to_extract_per_pass",
    )
    return parser.parse_args()


def _apply_overrides(cfg: Any, args: argparse.Namespace) -> None:
    overrides = {
        "max_iterations": args.max_iterations,
        "max_sources": args.max_sources,
        "max_results_per_query": args.max_results_per_query,
        "max_urls_to_extract_per_pass": args.extract_limit,
    }
    for attr, value in overrides.items():
        if value is not None:
            setattr(cfg, attr, value)


async def _run(args: argparse.Namespace) -> int:
    from services.deep_research.config import PHASE_TIMEOUTS, ResearchConfig
    import services.deep_research.dedup_filter as dedup_module
    from services.deep_research.content_profiles import apply_content_profile
    from services.deep_research.harvest import run_harvest
    from services.deep_research.logging_config import get_logger, start_new_run
    from services.deep_research.models import ResearchState
    from services.deep_research.orchestrator import (
        _harvest_timeout_for,
        _iterate,
        _run_phase,
        _synth_timeout,
    )
    from services.deep_research.plan import run_plan

    dump_path = args.out or _default_dump_path(args.depth)
    cfg = ResearchConfig.for_depth(args.depth)
    _apply_overrides(cfg, args)

    logger = get_logger()
    state = ResearchState(question=args.question, config=cfg, _logger=logger)
    phase_results: list[dict[str, Any]] = []
    dumper = FilteredSourceDumper(
        path=dump_path,
        question=args.question,
        depth=args.depth,
        unique_only=not args.include_duplicates,
    )

    original_run_dedup_filter = dedup_module.run_dedup_filter
    dedup_pass = {"count": 0}

    async def dumping_run_dedup_filter(state_arg: ResearchState):
        result = await original_run_dedup_filter(state_arg)
        dedup_pass["count"] += 1
        dumper.dump_snapshot(
            state_arg,
            phase_label=f"dedup_filter_pass_{dedup_pass['count']}",
        )
        return result

    dedup_module.run_dedup_filter = dumping_run_dedup_filter

    status = "partial"
    try:
        start_new_run(logger, question=args.question, depth=args.depth)
        state.log(f"Deep Research source dump: '{args.question}'")
        state.log(
            f"  depth={args.depth} num_queries={cfg.num_queries} "
            f"max_sources={cfg.max_sources} dump={dump_path}"
        )

        plan_result = await _run_phase(state, phase_results, "plan", run_plan(state), PHASE_TIMEOUTS["plan"])
        if plan_result is None or not state.query_plans:
            state.error("Query planning failed")
            return 1

        state.search_queries = [plan.query for plan in state.query_plans]
        apply_content_profile(state)

        harvest_result = await _run_phase(
            state,
            phase_results,
            "harvest",
            run_harvest(state),
            _harvest_timeout_for(state),
        )
        if harvest_result is None or not state.extracted_sources:
            state.error("No sources harvested")
            return 1

        await _run_phase(
            state,
            phase_results,
            "dedup_filter",
            dedup_module.run_dedup_filter(state),
            PHASE_TIMEOUTS["dedup_filter"],
        )
        state.last_iteration_sources = list(state.extracted_sources)

        await _iterate(state, phase_results)

        if args.with_synthesis:
            from services.deep_research.synthesize import run_synthesize

            await _run_phase(
                state,
                phase_results,
                "synthesize",
                run_synthesize(state),
                _synth_timeout(state, args.depth),
            )
        else:
            state.log("Skipping synthesis; source dump is complete")

        status = "complete"
        return 0
    finally:
        dedup_module.run_dedup_filter = original_run_dedup_filter
        dumper.finish(status=status, errors=list(state.errors))
        state.log(f"Filtered-source dump saved to: {dump_path}")
        try:
            from core.llm.llm_client import close_session as _close_llm_session

            await _close_llm_session()
        except Exception:
            pass
        try:
            from services.web_search import shutdown_web_search

            await shutdown_web_search()
        except Exception:
            pass


def main() -> None:
    args = _parse_args()
    started = time.time()
    rc = asyncio.run(_run(args))
    print(f"done rc={rc} elapsed={time.time() - started:.1f}s")
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
