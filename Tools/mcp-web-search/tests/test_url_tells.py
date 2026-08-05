# Copyright NEXTGGTECH. Elastic License 2.0.

"""Offline coverage for the bad-site URL tells (identity-blind, zero-I/O).

Each tell must be gentle in isolation, the pack must cap, and — most importantly —
none of them may fire on the ordinary URLs that make up the bulk of real SERPs.
"""

from __future__ import annotations

from core.extract.scoring import query_terms
from core.search.quality import _SUSPICIOUS_PACK_CAP, emd_penalty, suspicious_url_penalty
from core.search.triage import TriageAction, TriageSession


# --- suspicious_url_penalty --------------------------------------------------------

def test_clean_urls_are_untouched():
    for url in (
        "https://www.anthropic.com/news/claude-sonnet-5",
        "https://docs.anthropic.com/en/docs/claude-code/overview",
        "https://github.com/anthropics/claude-code",
        "https://example.com.br/artigo",          # ccTLD second-level registry
        "https://example.co.uk/story",
        "https://en.wikipedia.org/wiki/Claude",
    ):
        assert suspicious_url_penalty(url) == 0.0, url


def test_ip_literal_and_port_tells():
    assert suspicious_url_penalty("https://203.0.113.7/download") < 0.0
    assert suspicious_url_penalty("https://site.example:8080/page") < 0.0
    assert suspicious_url_penalty("https://site.example:443/page") == 0.0


def test_embedded_gtld_costume():
    assert suspicious_url_penalty("https://github.com.evil-mirror.xyz/login") < 0.0
    # The real github.com must not trip its own name.
    assert suspicious_url_penalty("https://github.com/anthropics") == 0.0


def test_hyphen_and_year_stamped_names():
    assert suspicious_url_penalty("https://best-ai-coding-tools-2026.com/review") < 0.0
    assert suspicious_url_penalty("https://top10vpn2024.net/list") < 0.0
    # Two hyphens is ordinary branding, not a tell.
    assert suspicious_url_penalty("https://my-cool-site.com/post") == 0.0


def test_pack_is_capped():
    ugly = "https://github.com.best-free-vpn-review-2026.evil:8080/x"
    assert suspicious_url_penalty(ugly) == -_SUSPICIOUS_PACK_CAP


# --- emd_penalty ---------------------------------------------------------------------

def test_emd_hits_query_squatter():
    terms = tuple(query_terms("claude code official documentation"))
    assert emd_penalty("https://claudecode.pro/docs", terms) < 0.0
    assert emd_penalty("https://claude-code.dev/docs", terms) < 0.0


def test_emd_leaves_partial_and_official_domains_alone():
    terms = tuple(query_terms("claude code official documentation"))
    assert emd_penalty("https://claude.com/product/claude-code", terms) == 0.0
    assert emd_penalty("https://code.claude.com/docs", terms) == 0.0
    assert emd_penalty("https://github.com/anthropics", terms) == 0.0
    # Single-term queries never fire (every brand is its own exact match).
    assert emd_penalty("https://claudecode.pro/docs", tuple(query_terms("claudecode"))) == 0.0


# --- triage integration ----------------------------------------------------------------

def test_tells_demote_but_never_skip():
    session = TriageSession("claude code official documentation")
    clean = session.ingest_source(
        engine="google", provider_family="google", rank=1,
        url="https://docs.anthropic.com/claude-code",
        title="Claude Code official documentation",
        snippet="The official documentation for Claude Code: setup, usage and features.",
    )
    squatter = session.ingest_source(
        engine="google", provider_family="google", rank=2,
        url="https://claude-code-docs-2026.xyz/claude-code",
        title="Claude Code official documentation",
        snippet="The official documentation for Claude Code: setup, usage and features.",
    )
    assert clean.action == TriageAction.PARSE
    assert squatter.score < clean.score
    assert squatter.action != TriageAction.SKIP  # tells demote, they do not execute
