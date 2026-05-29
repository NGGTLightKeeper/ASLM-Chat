"""Tests for reputation content-quality signal, auto-promote, and trust wiring."""

from __future__ import annotations

import pytest

from core.extract.content_processor import PreviewPayload
from core.models.search import SearchResult
from core.registry.domain_reputation import (
    EMA_ALPHA,
    PROMOTE_MIN_OBS,
    PROMOTE_THRESHOLD,
    DomainReputationStore,
)
from services.web_search import (
    _PARSED_LEX_MARGIN,
    _content_quality_signal,
    _lexical_score,
    _parsed_lexical_score,
    _resolve_result_trust_tier,
    _result_score,
)


def _result(**kwargs) -> SearchResult:
    base = dict(
        url="https://security-notes.example/cve",
        title="CVE-2024 OpenSSL critical patch advisory",
        snippet="OpenSSL CVE-2024 critical patch RCE details and versions",
        engine="test",
    )
    base.update(kwargs)
    return SearchResult(**base)


def test_bm25_signal_can_exceed_promote_threshold() -> None:
    payload = PreviewPayload(
        text="CVE-2024-5535 CVSS 9.8. Upgrade OpenSSL 3.0.14.",
        quality_score=0.88,
        semantic_score=0.0,
    )
    result = _result(parsed_relevance_score=0.92, snippet_relevance_score=0.85)
    signal = _content_quality_signal(payload, result, "CVE-2024 OpenSSL critical patch RCE")
    assert signal >= PROMOTE_THRESHOLD, f"signal={signal:.3f} below promote threshold"


def test_bm25_signal_stays_below_promote_for_weak_preview() -> None:
    payload = PreviewPayload(text="Short.", quality_score=0.35, semantic_score=0.0)
    result = _result(parsed_relevance_score=0.25, snippet_relevance_score=0.30)
    signal = _content_quality_signal(payload, result, "CVE-2024 OpenSSL critical patch RCE")
    assert signal < PROMOTE_THRESHOLD


def test_semantic_path_uses_semantic_component() -> None:
    payload = PreviewPayload(text="Body", quality_score=0.7, semantic_score=0.85)
    result = _result(parsed_relevance_score=0.8)
    with_sem = _content_quality_signal(payload, result, "openssl patch")
    payload.semantic_score = 0.0
    without_sem = _content_quality_signal(payload, result, "openssl patch")
    assert with_sem != without_sem


def test_ema_reaches_promote_after_repeated_strong_signals() -> None:
    """Simulate EMA updates — strong BM25-era signals must converge above 0.72."""
    signal = 0.80
    ema = 0.5
    for _ in range(20):
        ema = EMA_ALPHA * signal + (1.0 - EMA_ALPHA) * ema
    assert ema >= PROMOTE_THRESHOLD


def _strong_bm25_observation() -> tuple[PreviewPayload, SearchResult, str, float]:
    """Realistic BM25-default observation that should eventually auto-promote."""
    query = "CVE-2024 OpenSSL critical patch RCE"
    payload = PreviewPayload(
        text="CVE-2024-5535 CVSS 9.8. Upgrade OpenSSL 3.0.14 and 3.1.6.",
        quality_score=0.88,
        semantic_score=0.0,
    )
    result = _result(parsed_relevance_score=0.92, snippet_relevance_score=0.85)
    signal = _content_quality_signal(payload, result, query)
    return payload, result, query, signal


@pytest.fixture
def rep_store(tmp_path) -> DomainReputationStore:
    return DomainReputationStore(str(tmp_path / "domain_reputation.db"))


def test_auto_promote_after_repeated_bm25_quality_observations(rep_store: DomainReputationStore) -> None:
    """BM25-era signals must drive per-query-type EMA over PROMOTE_THRESHOLD and set tier C."""
    domain = "security-notes.example"
    query_type = "technical"
    _, _, _, signal = _strong_bm25_observation()

    assert signal >= PROMOTE_THRESHOLD, f"fixture signal too weak: {signal:.3f}"

    for _ in range(PROMOTE_MIN_OBS):
        rep_store.record(domain, query_type, signal)

    report = rep_store.get_report(domain)
    assert report is not None
    qt_stats = report.per_type[query_type]
    assert qt_stats["ema"] >= PROMOTE_THRESHOLD
    assert qt_stats["obs"] >= PROMOTE_MIN_OBS
    assert rep_store.get_promoted_tier(domain) == "C"
    assert query_type in report.promoted_query_types


def test_parsed_lexical_beats_serp_only_when_body_matches_query() -> None:
    query = "CVE-2024 OpenSSL critical patch RCE"
    weak_snippet_result = _result(
        snippet="Click here for more information and subscribe today.",
        parsed_relevance_score=0.0,
        snippet_relevance_score=0.0,
    )
    body = (
        "CVE-2024-5535 OpenSSL critical patch RCE advisory. "
        "Upgrade OpenSSL 3.0.14 immediately. CVSS 9.8 critical."
    )
    payload = PreviewPayload(text=body, quality_score=0.85, semantic_score=0.0)

    serp_lex = _parsed_lexical_score(query, weak_snippet_result, PreviewPayload(text=""))
    parsed_lex = _parsed_lexical_score(query, weak_snippet_result, payload)
    assert parsed_lex > serp_lex
    assert parsed_lex >= 0.5

    profile = {"years": []}
    score_no_body = _result_score(
        weak_snippet_result,
        PreviewPayload(text=""),
        index=0,
        total=2,
        query=query,
        profile=profile,
    )
    score_with_body = _result_score(
        weak_snippet_result,
        payload,
        index=0,
        total=2,
        query=query,
        profile=profile,
    )
    assert score_with_body > score_no_body


def test_parsed_lex_boost_requires_margin_over_serp_lex() -> None:
    """No extra parsed_lex path when body does not beat SERP lexical by margin."""
    query = "CVE-2024 OpenSSL critical patch RCE"
    result = _result(
        title="CVE-2024 OpenSSL critical patch RCE advisory",
        snippet="CVE-2024 OpenSSL critical patch RCE details and versions",
    )
    payload = PreviewPayload(
        text="CVE-2024 OpenSSL critical patch RCE — short summary.",
        quality_score=0.82,
        semantic_score=0.0,
    )
    lex = _lexical_score(query, result.title, result.snippet, result.url)
    parsed_lex = _parsed_lexical_score(query, result, payload)
    assert parsed_lex <= lex + _PARSED_LEX_MARGIN + 1e-6

    profile = {"years": []}
    base_kw = dict(index=0, total=2, query=query, profile=profile)
    empty_payload = PreviewPayload(text="", quality_score=0.82, semantic_score=0.0)
    score_serp_only = _result_score(result, empty_payload, **base_kw)
    score_with_body = _result_score(result, payload, **base_kw)
    assert abs(score_with_body - score_serp_only) < 1e-6


def test_resolve_trust_tier_applies_auto_promoted_tier(rep_store: DomainReputationStore) -> None:
    """Promoted domain must surface as trust_tier B/C in triage/scoring paths."""
    domain = "openssl-notes.example"
    query_type = "technical"
    _, _, _, signal = _strong_bm25_observation()
    for _ in range(PROMOTE_MIN_OBS):
        rep_store.record(domain, query_type, signal)

    result = SearchResult(
        url=f"https://{domain}/advisory",
        title="OpenSSL advisory",
        snippet="patch",
        trust_tier="?",
    )
    _resolve_result_trust_tier(
        result,
        result.url,
        trust_reg=None,
        rep_store=rep_store,
    )
    assert result.trust_tier == "C"
