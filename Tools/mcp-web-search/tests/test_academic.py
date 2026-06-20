# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Offline tests for the academic vertical: registry load, per-provider parsers, the
cross-provider dedup/scoring, and the search-layer source adapter. No network."""

from __future__ import annotations

from core.fetch.academic.engine import AcademicSearchEngine
from core.fetch.academic.health import ProviderHealth
from core.fetch.academic.models import AcademicPaper
from core.fetch.academic.parse import (
    is_scholar_block,
    parse_arxiv,
    parse_crossref,
    parse_doaj,
    parse_europepmc,
    parse_openalex,
    parse_scholar,
)
from core.fetch.academic import providers as providers_mod
from core.fetch.academic.parse import parse_serpapi_scholar
from core.fetch.academic.providers import PROVIDERS, ranked_providers
from core.fetch.academic.registry import json_api_domains, load_registry


def test_registry_loads_friendly_json_apis():
    domains = load_registry()
    assert domains, "registry seed should load non-empty"
    patterns = {d.pattern for d in domains}
    assert {"openalex.org", "crossref.org", "arxiv.org"} <= patterns
    # json_api_domains keeps only keyless, text-search-capable REST endpoints.
    api_patterns = {d.pattern for d in json_api_domains()}
    assert "openalex.org" in api_patterns
    assert "unpaywall.org" not in api_patterns  # DOI-only (text_search_capable=False)


def test_every_wired_provider_maps_to_a_registry_row():
    for provider in PROVIDERS:
        assert provider.domain is not None, f"{provider.name} has no registry row"
    assert [p.name for p in ranked_providers()][0] == "openalex"  # highest weight


def test_parse_openalex_deinverts_abstract():
    body = {
        "results": [
            {
                "id": "https://openalex.org/W1",
                "display_name": "Attention Is All You Need",
                "doi": "https://doi.org/10.5555/abc",
                "publication_year": 2017,
                "cited_by_count": 99000,
                "open_access": {"is_oa": True, "oa_url": "https://x/paper.pdf"},
                "primary_location": {
                    "landing_page_url": "https://arxiv.org/abs/1706.03762",
                    "source": {"display_name": "NeurIPS"},
                },
                "authorships": [{"author": {"display_name": "A Vaswani"}}],
                "abstract_inverted_index": {"The": [0], "transformer": [1], "model": [2]},
            }
        ]
    }
    papers = parse_openalex(body)
    assert len(papers) == 1
    p = papers[0]
    assert p.title == "Attention Is All You Need"
    assert p.abstract == "The transformer model"
    assert p.doi == "10.5555/abc"
    assert p.year == 2017
    assert p.pdf_url.endswith(".pdf")
    assert p.venue == "NeurIPS"
    assert p.citations == 99000


def test_parse_crossref_strips_jats_abstract():
    body = {
        "message": {
            "items": [
                {
                    "DOI": "10.1/xyz",
                    "title": ["A Study"],
                    "abstract": "<jats:p>Hello <jats:italic>world</jats:italic></jats:p>",
                    "author": [{"given": "Jane", "family": "Doe"}],
                    "issued": {"date-parts": [[2020, 5]]},
                    "container-title": ["Nature"],
                    "is-referenced-by-count": 12,
                    "URL": "https://doi.org/10.1/xyz",
                }
            ]
        }
    }
    p = parse_crossref(body)[0]
    assert p.abstract == "Hello world"
    assert p.authors == ["Jane Doe"]
    assert p.year == 2020
    assert p.venue == "Nature"
    assert p.citations == 12


def test_parse_europepmc_and_doaj():
    epmc = parse_europepmc({
        "resultList": {"result": [{
            "id": "123", "source": "MED", "title": "Bio Paper",
            "authorString": "Smith J, Lee K", "abstractText": "Findings here.",
            "pubYear": "2019", "doi": "10.2/bio", "isOpenAccess": "Y",
            "journalInfo": {"journal": {"title": "Cell"}},
        }]}
    })[0]
    assert epmc.url.endswith("/MED/123")
    assert epmc.open_access is True
    assert epmc.authors == ["Smith J", "Lee K"]

    doaj = parse_doaj({
        "results": [{"id": "d1", "bibjson": {
            "title": "OA Article", "abstract": "Abstract.", "year": "2021",
            "author": [{"name": "R Roe"}],
            "identifier": [{"type": "doi", "id": "10.3000/oa"}],
            "link": [{"type": "fulltext", "url": "https://j/oa"}],
            "journal": {"title": "PLOS"},
        }}]
    })[0]
    assert doaj.doi == "10.3000/oa"
    assert doaj.open_access is True
    assert doaj.url == "https://j/oa"


def test_parse_arxiv_atom():
    xml = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/1234.5678</id>
        <title>Quantum Thing</title>
        <summary>We show a result.</summary>
        <published>2022-03-01T00:00:00Z</published>
        <author><name>P One</name></author>
        <author><name>Q Two</name></author>
        <link title="pdf" href="http://arxiv.org/pdf/1234.5678" type="application/pdf"/>
      </entry>
    </feed>"""
    p = parse_arxiv(xml)[0]
    assert p.title == "Quantum Thing"
    assert p.year == 2022
    assert p.pdf_url.endswith("1234.5678")
    assert p.authors == ["P One", "Q Two"]
    assert p.open_access is True


_SCHOLAR_HTML = """
<div class="gs_r gs_or gs_scl">
  <div class="gs_ggs gs_fl"><div class="gs_or_ggsm">
    <a href="https://x.org/paper.pdf">[PDF] x.org</a></div></div>
  <div class="gs_ri">
    <h3 class="gs_rt"><a href="https://x.org/abs">[PDF] Attention is all you need</a></h3>
    <div class="gs_a">A Vaswani, N Shazeer - Advances in NeurIPS, 2017 - proceedings.neurips.cc</div>
    <div class="gs_rs">We propose the Transformer, a model architecture eschewing recurrence.</div>
    <div class="gs_fl"><a href="/scholar?cites=1">Cited by 95,000</a><a href="#">Related</a></div>
  </div>
</div>
<div class="gs_r gs_or gs_scl">
  <div class="gs_ri">
    <h3 class="gs_rt"><a href="https://y.org/abs">BERT pre-training</a></h3>
    <div class="gs_a">J Devlin, MW Chang - 2019 - arxiv.org</div>
    <div class="gs_rs">Bidirectional Encoder Representations from Transformers.</div>
    <div class="gs_fl"><a href="/scholar?cites=2">Cited by 80,000</a></div>
  </div>
</div>
"""


def test_parse_scholar_html():
    papers = parse_scholar(_SCHOLAR_HTML)
    assert len(papers) == 2
    p = papers[0]
    assert p.title == "Attention is all you need"  # [PDF] tag stripped
    assert p.url == "https://x.org/abs"
    assert p.pdf_url == "https://x.org/paper.pdf"
    assert p.year == 2017
    assert p.citations == 95000
    assert "A Vaswani" in p.authors
    assert p.abstract.startswith("We propose the Transformer")
    assert papers[1].citations == 80000


def test_parse_serpapi_scholar():
    body = {
        "organic_results": [
            {
                "result_id": "abc",
                "title": "Attention is all you need",
                "link": "https://x.org/abs",
                "snippet": "We propose the Transformer.",
                "publication_info": {
                    "summary": "A Vaswani, N Shazeer - NeurIPS, 2017 - proceedings.neurips.cc",
                    "authors": [{"name": "A Vaswani"}, {"name": "N Shazeer"}],
                },
                "inline_links": {"cited_by": {"total": 95000}},
                "resources": [{"file_format": "PDF", "link": "https://x.org/p.pdf"}],
            }
        ]
    }
    p = parse_serpapi_scholar(body)[0]
    assert p.title == "Attention is all you need"
    assert p.source == "scholar"
    assert p.meta["via"] == "serpapi"
    assert p.year == 2017
    assert p.citations == 95000
    assert p.pdf_url == "https://x.org/p.pdf"
    assert p.authors == ["A Vaswani", "N Shazeer"]


def test_scholar_path_is_mutually_exclusive(monkeypatch):
    names = lambda: {p.name for p in ranked_providers()}
    monkeypatch.setattr(providers_mod, "_has_serpapi_key", lambda: True)
    with_key = names()
    assert "scholar_serpapi" in with_key and "scholar" not in with_key
    monkeypatch.setattr(providers_mod, "_has_serpapi_key", lambda: False)
    without_key = names()
    assert "scholar" in without_key and "scholar_serpapi" not in without_key


def test_scholar_block_detection():
    assert is_scholar_block('<html><body><div id="gs_captcha">...</div></body></html>')
    assert is_scholar_block('<form action="/sorry/index">please solve the captcha</form>' + "x" * 2100)
    assert not is_scholar_block(_SCHOLAR_HTML)
    assert not is_scholar_block("")  # trivial/empty body is not a block


def test_parsers_never_raise_on_garbage():
    assert parse_openalex({}) == []
    assert parse_crossref({"message": {}}) == []
    assert parse_doaj({"results": [None, 1, "x"]}) == []
    assert parse_arxiv("not xml <<<") == []


def test_dedupe_merges_by_doi_and_backfills():
    engine = AcademicSearchEngine()
    rich = AcademicPaper(id="a", title="Same Paper", url="u1", source="crossref",
                         source_domain="crossref.org", doi="10.1/same", citations=50)
    poor = AcademicPaper(id="b", title="Same Paper", url="u2", source="openalex",
                         source_domain="openalex.org", doi="10.1/same",
                         abstract="filled in", pdf_url="p.pdf", confidence=0.9)
    poor.confidence, rich.confidence = 0.9, 1.5  # rich wins
    out = engine._rank_and_dedupe([rich, poor], cap=10)
    assert len(out) == 1
    assert out[0].source == "crossref"
    assert out[0].abstract == "filled in"   # backfilled from the loser
    assert out[0].pdf_url == "p.pdf"
    assert "openalex" in out[0].meta.get("also_in", [])


def test_dual_key_dedup_collapses_doi_and_title():
    engine = AcademicSearchEngine()
    # OpenAlex carries a DOI; Scholar carries only a title — same paper, must merge to one.
    oa = AcademicPaper(id="o", title="Attention Is All You Need", url="u1",
                       source="openalex", source_domain="openalex.org",
                       doi="10.5555/aaaa", confidence=1.6)
    sch = AcademicPaper(id="s", title="attention is all you need", url="u2",
                        source="scholar", source_domain="scholar.google.com",
                        confidence=1.4)
    out = engine._rank_and_dedupe([oa, sch], cap=10)
    assert len(out) == 1
    assert "scholar" in out[0].meta.get("also_in", [])


def test_source_saturation_prevents_monopoly():
    engine = AcademicSearchEngine()
    papers = [AcademicPaper(id=f"o{i}", title=f"Open access study number {i}", url=f"o{i}",
                            source="openalex", source_domain="openalex.org",
                            confidence=1.5) for i in range(8)]
    papers += [AcademicPaper(id=f"e{i}", title=f"European medicine study {i}", url=f"e{i}",
                             source="europepmc", source_domain="europepmc.org",
                             confidence=1.3) for i in range(2)]
    out = engine._rank_and_dedupe(papers, cap=6)
    # Despite every openalex paper scoring higher, saturation must surface the other index.
    assert "europepmc" in {p.source for p in out}


def test_consensus_bonus_rewards_cross_index_agreement():
    engine = AcademicSearchEngine()
    solo = AcademicPaper(id="a", title="A unique solo paper title", url="a",
                         source="arxiv", source_domain="arxiv.org", confidence=1.2)
    p1 = AcademicPaper(id="b", title="An agreed upon paper title", url="b", source="openalex",
                       source_domain="openalex.org", doi="10.1234/agree", confidence=1.2)
    p2 = AcademicPaper(id="c", title="an agreed upon paper title", url="c", source="crossref",
                       source_domain="crossref.org", doi="10.1234/agree", confidence=1.0)
    out = engine._rank_and_dedupe([solo, p1, p2], cap=10)
    merged = next(p for p in out if p.source == "openalex")
    assert merged.meta.get("also_in") == ["crossref"]
    assert merged.confidence > 1.2  # agreement lifted it above its solo base score


def test_title_dedupe_when_no_doi():
    engine = AcademicSearchEngine()
    a = AcademicPaper(id="a", title="Deep Learning!", url="u1", source="arxiv",
                      source_domain="arxiv.org", confidence=1.0)
    b = AcademicPaper(id="b", title="deep   learning", url="u2", source="doaj",
                      source_domain="doaj.org", confidence=0.5)
    out = engine._rank_and_dedupe([a, b], cap=10)
    assert len(out) == 1


def test_provider_health_cools_down_on_repeated_antibot():
    h = ProviderHealth()
    assert h.available("doaj")
    h.record("doaj", ok=False, status_code=403)  # first antibot: still available
    assert h.available("doaj")
    h.record("doaj", ok=False, status_code=403)  # second: trips the cooldown
    assert not h.available("doaj")
    assert h.cooldown_remaining("doaj") > 0
    assert "doaj" in h.snapshot()
    # A clean 200 clears the streak and the cooldown.
    h.record("doaj", ok=True, status_code=200)
    assert h.available("doaj")


def test_provider_health_empty_200_is_not_a_failure():
    h = ProviderHealth()
    for _ in range(5):
        h.record("crossref", ok=False, status_code=200)  # 200, zero papers
    assert h.available("crossref")


def test_provider_health_min_interval_paces_fires():
    h = ProviderHealth()
    assert h.available("scholar", min_interval=4.0)
    h.note_fired("scholar")
    assert not h.available("scholar", min_interval=4.0)  # just fired, paced out
    assert h.available("scholar", min_interval=0.0)       # no pacing → always ok
    assert h.available("openalex", min_interval=4.0)       # different provider unaffected


def test_provider_health_backoff_is_exponential():
    h = ProviderHealth()
    for _ in range(2):
        h.record("arxiv", ok=False, error="ReadTimeout")
    first = h.cooldown_remaining("arxiv")
    h.record("arxiv", ok=False, error="ReadTimeout")
    second = h.cooldown_remaining("arxiv")
    assert second > first  # each further failure widens the cooldown


def test_search_layer_adapter_shapes_citable_source():
    from core.search.web_search import _academic_paper_dict

    paper = AcademicPaper(
        id="x", title="Title", url="https://u", source="openalex",
        source_domain="openalex.org", authors=["A", "B", "C", "D", "E"],
        abstract="An abstract.", year=2020, venue="NeurIPS", doi="10.1/x",
        citations=10, open_access=True, pdf_url="https://p.pdf", confidence=1.2,
    )
    d = _academic_paper_dict(paper, citation_id="S5", rank=5)
    assert d["kind"] == "academic"
    assert d["id"] == "S5"
    assert d["engine"] == "academic:openalex"
    assert "et al." in d["snippet"]
    assert d["doi"] == "10.1/x"
    assert d["pdf_url"] == "https://p.pdf"
