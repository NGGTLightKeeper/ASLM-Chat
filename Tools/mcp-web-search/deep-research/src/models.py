# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional


# Query planning models.
# Search query plan model.
@dataclass
class QueryPlan:
    """Store a search query together with routing hints."""

    query: str
    target_domains: list[str] = field(default_factory=list)
    method_hint: str = "auto"


# Search result models.
# Unified search result model.
@dataclass
class SearchResult:
    """Represent one search result returned by any backend."""

    url: str
    title: str
    snippet: str
    engine: str = ""
    trust_tier: str = "?"
    score: float = 0.0
    method_hint: str = ""
    extract_debug_stage: str = ""
    extract_debug_timeout_sec: float = 0.0


# Extracted source models.
# Extracted source content model.
@dataclass
class ExtractedSource:
    """Store extracted content and downstream enrichment fields."""

    url: str
    title: str
    text: str
    char_count: int = 0
    extraction_method: str = "trafilatura"
    content_hash: str = ""
    entities: list[dict[str, Any]] = field(default_factory=list)
    relevant_chunks: str = ""
    summary: str = ""
    # Triage metadata (populated by LLM triage step).
    sub_topic: str = ""
    content_type: str = ""
    evidence_strength: str = ""
    source_character: str = ""
    perspective: str = ""


# Research state models.
# Shared pipeline state model.
@dataclass
class ResearchState:
    """Keep mutable state shared across the deep-research pipeline."""

    question: str
    config: object
    query_type: str = "general"
    search_queries: list[str] = field(default_factory=list)
    query_plans: list[QueryPlan] = field(default_factory=list)
    raw_results: list[SearchResult] = field(default_factory=list)
    extracted_sources: list[ExtractedSource] = field(default_factory=list)
    last_iteration_sources: list[ExtractedSource] = field(default_factory=list)
    synthesis_batch_reports: list[str] = field(default_factory=list)
    final_report: str = ""
    log_lines: list[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    errors: list[str] = field(default_factory=list)
    log_file: Optional[str] = None

    # Logging helpers.
    def log(self, message: str) -> None:
        """Append a timestamped log line and mirror it to stderr."""

        elapsed = time.time() - self.start_time
        line = f"[{elapsed:6.1f}s] {message}"
        self.log_lines.append(line)
        print(line, file=sys.stderr, flush=True)

        # Mirror logs into a file when the pipeline is configured to persist them.
        if self.log_file:
            try:
                with open(self.log_file, "a", encoding="utf-8") as file_obj:
                    file_obj.write(line + "\n")
            except Exception:
                pass

    # Error helpers.
    def error(self, message: str) -> None:
        """Record an error message and send it through the logger."""

        self.errors.append(message)
        self.log(f"ERROR: {message}")


    # Derived state helpers.
    # Return the elapsed runtime.
    @property
    def elapsed(self) -> float:
        """Return the elapsed runtime in seconds."""

        return time.time() - self.start_time

    # Derived state helpers.
    # Return the extracted source count.
    @property
    def source_count(self) -> int:
        """Return the number of extracted sources."""

        return len(self.extracted_sources)
