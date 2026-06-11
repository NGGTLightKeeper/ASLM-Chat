"""Search-core orchestration primitives."""

from .triage import (
    TIER_TRUST_SCORES,
    TriageResult,
    TriageSession,
    apply_candidate_scores,
    apply_registry_routing,
    resolve_result_trust_tier,
    triage_one_result,
    triage_results,
    triage_soft_score,
)

__all__ = [
    "TIER_TRUST_SCORES",
    "TriageResult",
    "TriageSession",
    "apply_candidate_scores",
    "apply_registry_routing",
    "resolve_result_trust_tier",
    "triage_one_result",
    "triage_results",
    "triage_soft_score",
]
