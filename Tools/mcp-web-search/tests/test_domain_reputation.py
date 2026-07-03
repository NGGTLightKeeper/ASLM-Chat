# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Offline coverage for the runtime domain-reputation layer.

Guards the anti-recursion contract: raw counters only, penalty computed at read
time with a hard cap, TTL/decay as the rehabilitation path, and triage penalties
that nudge without ever executing (SKIP is reputation-blind).
"""

from __future__ import annotations

import time

import pytest

from core.profiles import ReputationSnapshot
from core.profiles.runtime_profiles import (
    _REP_TOTAL_CAP,
    _TTL_SECONDS,
    RuntimeDomainProfiles,
)
from core.search.quality import insecure_scheme_penalty, is_established_tld
from core.search.triage import (
    _PARSE_THRESHOLD,
    _UNPROVEN_PARSE_MARGIN,
    TriageAction,
    TriageSession,
)


@pytest.fixture()
def store(tmp_path) -> RuntimeDomainProfiles:
    return RuntimeDomainProfiles(str(tmp_path / "runtime.db"))


# --- reputation store ------------------------------------------------------------

def test_single_tls_failure_is_not_penalised(store):
    store.record_reputation("https://blip.example/x", tls_failed=True)
    assert "blip.example" not in store.reputation_snapshot().penalties


def test_repeat_tls_failures_earn_capped_penalty(store):
    for _ in range(10):
        store.record_reputation("https://broken.example/x", tls_failed=True)
    penalties = store.reputation_snapshot().penalties
    assert penalties["broken.example"] > 0.0
    assert penalties["broken.example"] <= _REP_TOTAL_CAP  # hard ceiling, however bad


def test_successful_parse_clears_tls_penalty(store):
    # A host that recovered (fixed its certificate) sheds the penalty immediately.
    store.record_reputation("https://healed.example/x", tls_failed=True)
    store.record_reputation("https://healed.example/x", tls_failed=True)
    assert "healed.example" in store.reputation_snapshot().penalties
    store.record_reputation("https://healed.example/x", parse_ok=True)
    assert "healed.example" not in store.reputation_snapshot().penalties


def test_empty_parse_ratio_needs_sample_and_majority(store):
    # Two empties — below the minimum sample: no penalty.
    store.record_reputation("https://thin.example/a", parse_empty=True)
    store.record_reputation("https://thin.example/b", parse_empty=True)
    assert "thin.example" not in store.reputation_snapshot().penalties
    # Third empty crosses the sample bar with a 100% empty share.
    store.record_reputation("https://thin.example/c", parse_empty=True)
    assert store.reputation_snapshot().penalties["thin.example"] > 0.0


def test_successes_offset_empty_parses(store):
    # Half empty / half ok — not "systematic", no penalty.
    for i in range(3):
        store.record_reputation(f"https://mixed.example/{i}", parse_empty=True)
        store.record_reputation(f"https://mixed.example/ok{i}", parse_ok=True)
    assert "mixed.example" not in store.reputation_snapshot().penalties


def test_proven_domains_have_recent_successful_parses(store):
    store.record_reputation("https://solid.example/a", parse_ok=True)
    store.record_reputation("https://solid.example/b", parse_ok=True)
    snapshot = store.reputation_snapshot()
    assert "solid.example" in snapshot.proven
    assert "solid.example" not in snapshot.penalties


def test_penalty_expires_after_ttl(store, monkeypatch):
    store.record_reputation("https://old.example/x", tls_failed=True)
    store.record_reputation("https://old.example/x", tls_failed=True)
    assert "old.example" in store.reputation_snapshot().penalties
    # The only road back is fresh observations — silence alone ages the grudge out.
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + _TTL_SECONDS + 60)
    assert "old.example" not in store.reputation_snapshot().penalties


def test_stale_epoch_counters_reset_on_next_write(store, monkeypatch):
    store.record_reputation("https://reborn.example/x", tls_failed=True)
    store.record_reputation("https://reborn.example/x", tls_failed=True)
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + _TTL_SECONDS + 60)
    # One fresh failure after a stale epoch starts from zero — below the repeat bar.
    store.record_reputation("https://reborn.example/x", tls_failed=True)
    assert "reborn.example" not in store.reputation_snapshot().penalties


# --- TLD tiers & scheme ------------------------------------------------------------

def test_established_tlds():
    assert is_established_tld("example.com")
    assert is_established_tld("gov.uk")            # ccTLD
    assert is_established_tld("пример.xn--p1ai")   # IDN ccTLD (.рф)
    assert not is_established_tld("myengineeringpath.dev")
    assert not is_established_tld("slop.xyz")


def test_insecure_scheme_penalty():
    assert insecure_scheme_penalty("http://old.example/a") < 0.0
    assert insecure_scheme_penalty("https://ok.example/a") == 0.0


# --- triage integration --------------------------------------------------------------

_TITLE = "Python asyncio tutorial"
_SNIPPET = "A long, detailed walkthrough of asyncio coroutines and tasks in Python."


def _ingest(session: TriageSession, url: str, *, engine="google", family="google", rank=1):
    return session.ingest_source(
        engine=engine, provider_family=family, rank=rank, url=url,
        title=_TITLE, snippet=_SNIPPET,
    )


def test_penalised_domain_loses_parse_slot_but_is_not_skipped():
    clean = TriageSession("python asyncio tutorial")
    baseline = _ingest(clean, "https://ex.com/a")
    assert baseline.action == TriageAction.PARSE

    snapshot = ReputationSnapshot(penalties={"ex.com": 0.25}, proven=frozenset())
    session = TriageSession("python asyncio tutorial", reputation=snapshot)
    decision = _ingest(session, "https://ex.com/a")
    assert decision.score == pytest.approx(baseline.score - 0.25, abs=1e-6)
    assert decision.action == TriageAction.QUEUE  # nudged out of the slot, not executed


def test_consensus_outvotes_reputation_penalty():
    snapshot = ReputationSnapshot(penalties={"ex.com": 0.25}, proven=frozenset())
    session = TriageSession("python asyncio tutorial", reputation=snapshot)
    assert _ingest(session, "https://ex.com/a").action == TriageAction.QUEUE
    upgraded = session.ingest_vote(provider_family="yandex", url="https://ex.com/a")
    assert upgraded is not None and upgraded.action == TriageAction.PARSE


def test_unproven_tld_single_family_needs_stricter_bar():
    # Same SERP evidence: the .com parses, the unknown .dev waits in the queue…
    session = TriageSession("python asyncio tutorial")
    com = _ingest(session, "https://ex.com/a", rank=6)
    dev = _ingest(session, "https://myengineeringpath.dev/a", rank=6)
    assert com.action == TriageAction.PARSE
    assert _PARSE_THRESHOLD <= dev.score < _PARSE_THRESHOLD + _UNPROVEN_PARSE_MARGIN
    assert dev.action == TriageAction.QUEUE
    # …until a second independent family vouches for it.
    upgraded = session.ingest_vote(provider_family="yandex", url="https://myengineeringpath.dev/a")
    assert upgraded is not None and upgraded.action == TriageAction.PARSE


def test_proven_history_exempts_unproven_tld():
    # rank=6 lands between the normal and strict bars, so the exemption is what decides.
    snapshot = ReputationSnapshot(penalties={}, proven=frozenset({"myengineeringpath.dev"}))
    session = TriageSession("python asyncio tutorial", reputation=snapshot)
    decision = _ingest(session, "https://myengineeringpath.dev/a", rank=6)
    assert decision.action == TriageAction.PARSE
