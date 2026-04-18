# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Configuration for the agentic deep research runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass

SYNTH_CHAR_BUDGET_PER_SOURCE: int = 2_000


# Per-content-type budget multipliers for max_search_calls and max_read_calls.
# "general" is the baseline (no overrides applied).
_CONTENT_PROFILES: dict[str, dict[str, int]] = {
    # Deep technical questions need thorough source reading; moderate search breadth.
    "technical": {"max_search_calls": 12, "max_read_calls": 22},
    # Academic/research questions benefit from many sources and deep reads.
    "academic":  {"max_search_calls": 14, "max_read_calls": 24},
    # News/current events: breadth of sources over deep reading.
    "news":      {"max_search_calls": 16, "max_read_calls": 10},
    # How-to/tutorial questions need more reading for concrete steps.
    "how_to":    {"max_search_calls": 11, "max_read_calls": 20},
    # General: baseline defaults, no overrides.
    "general":   {},
}

_TECHNICAL_KW = {"install", "configure", "setup", "deploy", "debug", "error", "fix", "api",
                 "code", "library", "framework", "docker", "kubernetes", "server", "database",
                 "dependency", "build", "compile", "integrate", "migration"}
_ACADEMIC_KW  = {"research", "study", "paper", "review", "analysis", "literature", "journal",
                 "experiment", "hypothesis", "methodology", "findings", "citation", "arxiv",
                 "survey", "meta-analysis", "systematic"}
_NEWS_KW      = {"news", "latest", "today", "current", "recent", "update", "announcement",
                 "release", "2024", "2025", "2026", "breaking", "event", "happened"}
_HOW_TO_KW    = {"how to", "how do", "step by step", "tutorial", "guide", "walkthrough",
                 "instructions", "procedure", "example", "sample"}


def _detect_content_type(question: str) -> str:
    """Classify the research question into a content type for budget tuning."""
    import re as _re
    q = question.lower()
    words = set(_re.findall(r"[a-z0-9]+", q))

    def _matches(kw_set: set[str]) -> bool:
        for kw in kw_set:
            if " " in kw:  # phrase: substring match
                if kw in q:
                    return True
            else:           # single word: whole-word match
                if kw in words:
                    return True
        return False

    # how-to must be checked before technical (overlap on "install", "configure")
    if _matches(_HOW_TO_KW):
        return "how_to"
    if _matches(_NEWS_KW):
        return "news"
    if _matches(_ACADEMIC_KW):
        return "academic"
    if _matches(_TECHNICAL_KW):
        return "technical"
    return "general"


@dataclass
class ResearchConfig:
    """Runtime budgets and model settings for agentic deep research."""

    depth: str = "standard"
    content_type: str = "general"

    # Controller loop
    max_steps: int = 30
    max_search_calls: int = 10
    max_read_calls: int = 16
    max_python_calls: int = 5
    max_reflect_without_tool: int = 2
    min_search_calls_before_finish: int = 2
    min_read_calls_before_finish: int = 4

    # Extra quota granted when model explicitly requests it (once per session).
    extra_quota_search_calls: int = 7
    extra_quota_read_calls: int = 7
    total_timeout_sec: float = 1800.0
    synthesis_reserve_sec: float = 360.0
    controller_timeout_sec: float = 90.0

    # Source and context budgets
    max_sources: int = 90
    search_results_per_call: int = 12
    synthesis_context_budget: int = 120_000
    synthesis_buffer_pct: float = 0.18  # reserve 18% of budget for synthesis pass
    read_page_max_chars: int = 32_000
    read_chunk_chars: int = 6_000
    read_chunk_overlap: int = 300
    tool_observation_max_chars: int = 6_000
    read_wayback_fallback: bool = True

    # Pre-synthesis artifact compression pass.
    # Triggered when total read-artifact content exceeds the threshold.
    # Batches artifacts into chunks, asks LLM to extract primary claims per batch,
    # then passes the compressed essays to the final synthesis call instead of raw content.
    artifact_compression_threshold_chars: int = 30_000
    artifact_compression_batch_chars: int = 20_000
    artifact_compression_output_chars: int = 8_000

    # Tool timeouts
    search_timeout_sec: float = 30.0
    read_timeout_sec: float = 25.0
    python_timeout_sec: int = 20

    # Model settings
    query_model: str = "local-model"
    synthesis_model: str = ""
    controller_temperature: float = 0.35
    synthesis_temperature: float = 0.25
    structured_output_enabled: bool = True
    structured_output_strict: bool = True

    # Python backend: "deep_think" | "mcp_sandbox" | "disabled"
    python_backend: str = "deep_think"

    # Local run artifacts. Pytest disables this automatically to avoid test churn.
    write_logs: bool = os.getenv("MCP_WEB_SEARCH_DEEP_RESEARCH_LOGS", "1").strip().lower() not in {"0", "false", "no", "off"}

    @classmethod
    def for_depth(cls, depth: str) -> "ResearchConfig":
        """Return the baseline research config (depth accepted for API compatibility)."""
        cfg = cls()
        cfg.depth = "standard"
        return cfg

    @classmethod
    def for_question(cls, question: str, depth: str = "standard") -> "ResearchConfig":
        """Return a config with tool budgets tuned to the detected content type."""
        cfg = cls.for_depth(depth)
        cfg.content_type = _detect_content_type(question)
        for key, value in _CONTENT_PROFILES.get(cfg.content_type, {}).items():
            setattr(cfg, key, value)
        return cfg

    @property
    def research_deadline_sec(self) -> float:
        """Time budget for tool use before synthesis must start."""

        total = max(1.0, float(self.total_timeout_sec))
        reserve = min(total * 0.5, max(30.0, float(self.synthesis_reserve_sec)))
        floor = 60.0 if total >= 120.0 else max(1.0, total * 0.5)
        return max(floor, total - reserve)

    @property
    def effective_tool_context_budget(self) -> int:
        """Context characters available for tool output (excludes synthesis reserve).

        Reserves ``synthesis_buffer_pct`` of ``synthesis_context_budget`` so the
        synthesis LLM pass always has headroom to run without being starved.

        Example: budget=120_000, buffer=18% → tools can consume up to ~98_400 chars.
        """
        budget = max(1, int(self.synthesis_context_budget))
        return int(budget * (1.0 - max(0.0, min(0.5, float(self.synthesis_buffer_pct)))))
