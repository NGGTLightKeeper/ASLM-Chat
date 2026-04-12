# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Data models for the deep research pipeline.

Pure data containers: QueryPlan, ExtractedSource, ResearchState, PhaseResult.
Configuration (ResearchConfig, PHASE_TIMEOUTS, etc.) lives in config.py.
ResearchConfig is re-exported here for backward compatibility.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional

# Re-export so callers that do `from services.deep_research.models import ResearchConfig`
# continue to work without changes.
from services.deep_research.config import ResearchConfig  # noqa: F401
from core.models.search import SearchResult


# ---------------------------------------------------------------------------
# Query plan
# ---------------------------------------------------------------------------

@dataclass
class QueryPlan:
    """One planned search query with optional domain routing."""

    query: str
    target_domains: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extracted source
# ---------------------------------------------------------------------------

@dataclass
class ExtractedSource:
    """One extracted source with downstream enrichment fields."""

    url: str
    title: str
    text: str
    char_count: int = 0
    extraction_method: str = "page_fetcher"
    content_hash: str = ""
    relevant_chunks: str = ""
    summary: str = ""
    entities: list[dict[str, Any]] = field(default_factory=list)
    # Triage metadata (Phase 3)
    sub_topic: str = ""
    content_type: str = ""
    evidence_strength: str = ""
    source_character: str = ""
    perspective: str = ""
    # Scoring
    relevance_score: float = 0.0


# ---------------------------------------------------------------------------
# Research state
# ---------------------------------------------------------------------------

@dataclass
class ResearchState:
    """Mutable state shared across all pipeline phases."""

    question: str
    config: ResearchConfig
    query_type: str = "general"
    search_queries: list[str] = field(default_factory=list)
    query_plans: list[QueryPlan] = field(default_factory=list)
    raw_urls: set[str] = field(default_factory=set)
    raw_results: list[SearchResult] = field(default_factory=list)
    extracted_sources: list[ExtractedSource] = field(default_factory=list)
    last_iteration_sources: list[ExtractedSource] = field(default_factory=list)
    synthesis_batch_reports: list[str] = field(default_factory=list)
    final_report: str = ""
    completed_phases: list[str] = field(default_factory=list)
    log_lines: list[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    errors: list[str] = field(default_factory=list)
    failed_queries: list[str] = field(default_factory=list)
    attempted_followups: list[str] = field(default_factory=list)
    # Per-iteration gap history: each entry is the list of gap strings from one reflection call.
    # Used to detect stagnation when the same gaps keep reappearing.
    iteration_gaps: list[list[str]] = field(default_factory=list)

    # Logger reference; set by orchestrator from logging_config
    _logger: Optional[Any] = field(default=None, repr=False)
    # CoT sink: callable(thinking: str, iteration: int) → None; set by orchestrator
    cot_sink: Optional[Any] = field(default=None, repr=False)
    # Counter incremented by reflection on each call — used to label CoT log sections
    _reflection_count: int = field(default=0, repr=False)

    def log(self, message: str) -> None:
        """Timestamped log line → file + stderr."""
        elapsed = time.time() - self.start_time
        line = f"[{elapsed:6.1f}s] {message}"
        self.log_lines.append(line)
        print(line, file=sys.stderr, flush=True)
        if self._logger:
            self._logger.info(line)

    def error(self, message: str) -> None:
        self.errors.append(message)
        self.log(f"ERROR: {message}")

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    @property
    def source_count(self) -> int:
        return len(self.extracted_sources)


# ---------------------------------------------------------------------------
# Phase results (returned by each phase for orchestrator tracking)
# ---------------------------------------------------------------------------

@dataclass
class PhaseResult:
    """Lightweight envelope returned by each pipeline phase."""

    phase_name: str
    success: bool = True
    items_produced: int = 0
    duration_sec: float = 0.0
    error: str = ""
