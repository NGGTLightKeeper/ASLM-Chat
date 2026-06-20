from __future__ import annotations

from core.models.search import SearchResult
from core.query.routing_score import QueryClassWeight
from core.search.triage import (
    apply_candidate_scores,
    apply_registry_routing,
    TriageSession,
    triage_one_result,
    triage_soft_score,
)
from services.web_search import _triage_one_result


def _result() -> SearchResult:
    return SearchResult(
        url="https://docs.python.org/3/howto/free-threading-python.html",
        title="Python support for free threading",
        snippet="Official Python documentation covering free-threaded CPython builds in detail.",
        engine="fixture",
    )


def test_search_core_attaches_streamed_decoder_scores() -> None:
    results = [_result(), _result()]

    scores = apply_candidate_scores(
        results,
        [1.4, -0.2],
        debug_key="decoder",
        debug_values=[["relevant"], ["irrelevant"]],
    )

    assert scores == [1.0, 0.0]
    assert results[0].snippet_relevance_score == 1.0
    assert results[1].routing_debug["decoder"] == ["irrelevant"]


def test_search_core_applies_json_registry_routing() -> None:
    result = _result()

    apply_registry_routing([result], [QueryClassWeight("documentation", 1.0)])

    assert result.routing_score > 0.0
    assert "domain_method" in result.routing_debug


def test_web_search_compatibility_wrapper_matches_core_triage() -> None:
    direct = _result()
    wrapped = _result()

    expected = triage_one_result(direct, "Python free threading docs", index=0, total=1)
    actual = _triage_one_result(wrapped, "Python free threading docs", index=0, total=1)

    assert actual.skip == expected.skip
    assert actual.fetch_policy == expected.fetch_policy
    assert actual.score == expected.score


def test_streaming_triage_session_applies_registry_and_decoder_score() -> None:
    result = _result()
    session = TriageSession(
        "Python free threading docs",
        [QueryClassWeight("documentation", 1.0)],
        expected_total=5,
    )

    decision = session.ingest(result, decoder_score=0.9, decoder_debug=["relevant"])

    assert decision.skip is False
    assert result.routing_score > 0.0
    assert result.snippet_relevance_score == 0.9
    assert result.routing_debug["snippet_decoder_top"] == ["relevant"]


def test_cross_engine_consensus_adds_bounded_triage_boost() -> None:
    single = _result()
    consensus = _result()
    consensus.consensus_votes = 3
    consensus.consensus_engines = ["google", "brave", "stackoverflow"]

    single_score = triage_soft_score(single, "Python free threading docs", index=0, total=3)
    consensus_score = triage_soft_score(consensus, "Python free threading docs", index=0, total=3)

    assert consensus_score > single_score
    assert consensus_score - single_score <= 0.12
