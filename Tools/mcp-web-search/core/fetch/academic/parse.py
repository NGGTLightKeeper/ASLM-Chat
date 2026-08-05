# Copyright NEXTGGTECH. Elastic License 2.0.

"""Normalize each provider's reply into a flat list of AcademicPaper records.

Every scholarly API returns a different shape (OpenAlex inverts its abstract into a
position index, Crossref ships JATS-XML abstracts, arXiv is Atom). Each parser is
defensive: a malformed or missing field yields an empty/partial record, never an
exception, so one bad row can't sink the provider.
"""

from __future__ import annotations

import re
from typing import Any
import xml.etree.ElementTree as ET

from .models import AcademicPaper

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_DOI_RE = re.compile(r"10\.\d{4,9}/\S+")
_MAX_ABSTRACT = 1500


def _clean(text: str) -> str:
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", str(text or ""))).strip()


def _abstract(text: str) -> str:
    cleaned = _clean(text)
    return cleaned[:_MAX_ABSTRACT].rsplit(" ", 1)[0] if len(cleaned) > _MAX_ABSTRACT else cleaned


def _doi(value: str) -> str:
    m = _DOI_RE.search(str(value or ""))
    return m.group(0).rstrip(".,;)").lower() if m else ""


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# OpenAlex stores the abstract as {word: [positions]} — reassemble it in order.
def _deinvert_abstract(index: dict[str, list[int]] | None) -> str:
    if not isinstance(index, dict) or not index:
        return ""
    slots: list[tuple[int, str]] = []
    for word, positions in index.items():
        for pos in positions or []:
            if isinstance(pos, int):
                slots.append((pos, word))
    slots.sort(key=lambda s: s[0])
    return _abstract(" ".join(word for _, word in slots))


def parse_openalex(body: dict[str, Any]) -> list[AcademicPaper]:
    out: list[AcademicPaper] = []
    for work in body.get("results", []) or []:
        if not isinstance(work, dict):
            continue
        doi = _doi(work.get("doi") or "")
        oa = work.get("open_access") or {}
        loc = work.get("primary_location") or {}
        venue = ""
        if isinstance(loc.get("source"), dict):
            venue = str(loc["source"].get("display_name") or "")
        authors = [
            str((a.get("author") or {}).get("display_name") or "")
            for a in work.get("authorships", []) or []
            if isinstance(a, dict)
        ]
        url = str(loc.get("landing_page_url") or work.get("id") or "")
        out.append(AcademicPaper(
            id=str(work.get("id") or doi or url),
            title=_clean(work.get("display_name") or work.get("title") or ""),
            url=url,
            source="openalex",
            source_domain="openalex.org",
            authors=[a for a in authors if a],
            abstract=_deinvert_abstract(work.get("abstract_inverted_index")),
            year=_int(work.get("publication_year")),
            venue=_clean(venue),
            doi=doi,
            pdf_url=str(oa.get("oa_url") or ""),
            open_access=bool(oa.get("is_oa")),
            citations=_int(work.get("cited_by_count")),
        ))
    return out


def parse_crossref(body: dict[str, Any]) -> list[AcademicPaper]:
    items = (body.get("message") or {}).get("items", []) or []
    out: list[AcademicPaper] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = ""
        if isinstance(it.get("title"), list) and it["title"]:
            title = str(it["title"][0])
        authors = [
            " ".join(p for p in (str(a.get("given") or ""), str(a.get("family") or "")) if p)
            for a in it.get("author", []) or []
            if isinstance(a, dict)
        ]
        year = None
        parts = (it.get("issued") or {}).get("date-parts") or []
        if parts and isinstance(parts[0], list) and parts[0]:
            year = _int(parts[0][0])
        venue = ""
        if isinstance(it.get("container-title"), list) and it["container-title"]:
            venue = str(it["container-title"][0])
        pdf = ""
        for link in it.get("link", []) or []:
            if isinstance(link, dict) and "pdf" in str(link.get("content-type") or "").lower():
                pdf = str(link.get("URL") or "")
                break
        out.append(AcademicPaper(
            id=str(it.get("DOI") or it.get("URL") or title),
            title=_clean(title),
            url=str(it.get("URL") or ""),
            source="crossref",
            source_domain="crossref.org",
            authors=[a for a in authors if a],
            abstract=_abstract(it.get("abstract") or ""),
            year=year,
            venue=_clean(venue),
            doi=_doi(it.get("DOI") or ""),
            pdf_url=pdf,
            citations=_int(it.get("is-referenced-by-count")),
        ))
    return out


def parse_europepmc(body: dict[str, Any]) -> list[AcademicPaper]:
    results = (body.get("resultList") or {}).get("result", []) or []
    out: list[AcademicPaper] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        pdf = ""
        for grp in (r.get("fullTextUrlList") or {}).get("fullTextUrl", []) or []:
            if isinstance(grp, dict) and str(grp.get("documentStyle") or "").lower() == "pdf":
                pdf = str(grp.get("url") or "")
                break
        venue = ""
        ji = r.get("journalInfo") or {}
        if isinstance(ji.get("journal"), dict):
            venue = str(ji["journal"].get("title") or "")
        doi = _doi(r.get("doi") or "")
        ext_id, src = str(r.get("id") or ""), str(r.get("source") or "")
        url = f"https://europepmc.org/article/{src}/{ext_id}" if ext_id and src else ""
        out.append(AcademicPaper(
            id=str(doi or (src + ext_id) or r.get("title")),
            title=_clean(r.get("title") or ""),
            url=url,
            source="europepmc",
            source_domain="europepmc.org",
            authors=[a for a in str(r.get("authorString") or "").split(", ") if a],
            abstract=_abstract(r.get("abstractText") or ""),
            year=_int(r.get("pubYear")),
            venue=_clean(venue),
            doi=doi,
            pdf_url=pdf,
            open_access=str(r.get("isOpenAccess") or "").upper() == "Y",
            citations=_int(r.get("citedByCount")),
        ))
    return out


def parse_doaj(body: dict[str, Any]) -> list[AcademicPaper]:
    out: list[AcademicPaper] = []
    for row in body.get("results", []) or []:
        bj = row.get("bibjson") if isinstance(row, dict) else None
        if not isinstance(bj, dict):
            continue
        doi = ""
        for ident in bj.get("identifier", []) or []:
            if isinstance(ident, dict) and str(ident.get("type") or "").lower() == "doi":
                doi = _doi(ident.get("id") or "")
        url = ""
        for link in bj.get("link", []) or []:
            if isinstance(link, dict) and str(link.get("type") or "").lower() == "fulltext":
                url = str(link.get("url") or "")
                break
        authors = [
            str(a.get("name") or "") for a in bj.get("author", []) or [] if isinstance(a, dict)
        ]
        journal = bj.get("journal") if isinstance(bj.get("journal"), dict) else {}
        out.append(AcademicPaper(
            id=str(row.get("id") or doi or url),
            title=_clean(bj.get("title") or ""),
            url=url or (f"https://doi.org/{doi}" if doi else ""),
            source="doaj",
            source_domain="doaj.org",
            authors=[a for a in authors if a],
            abstract=_abstract(bj.get("abstract") or ""),
            year=_int(bj.get("year")),
            venue=_clean(journal.get("title") or ""),
            doi=doi,
            open_access=True,  # DOAJ is open-access by definition
        ))
    return out


_ATOM = "{http://www.w3.org/2005/Atom}"


def parse_arxiv(xml_text: str) -> list[AcademicPaper]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out: list[AcademicPaper] = []
    for entry in root.findall(f"{_ATOM}entry"):
        abs_url = (entry.findtext(f"{_ATOM}id") or "").strip()
        pdf = ""
        for link in entry.findall(f"{_ATOM}link"):
            if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                pdf = link.get("href") or ""
        authors = [
            (a.findtext(f"{_ATOM}name") or "").strip()
            for a in entry.findall(f"{_ATOM}author")
        ]
        published = (entry.findtext(f"{_ATOM}published") or "")[:4]
        out.append(AcademicPaper(
            id=abs_url,
            title=_clean(entry.findtext(f"{_ATOM}title") or ""),
            url=abs_url,
            source="arxiv",
            source_domain="arxiv.org",
            authors=[a for a in authors if a],
            abstract=_abstract(entry.findtext(f"{_ATOM}summary") or ""),
            year=_int(published) if published.isdigit() else None,
            venue="arXiv",
            pdf_url=pdf,
            open_access=True,
        ))
    return out


_CITED_BY_RE = re.compile(r"cited by\s+([\d,]+)", re.IGNORECASE)
_YEAR_IN_META_RE = re.compile(r"\b(19|20)\d{2}\b")
# Markers Google Scholar serves on a 200 CAPTCHA / "unusual traffic" wall instead of results.
_SCHOLAR_BLOCK_MARKERS = (
    "gs_captcha", "id=\"gs_captcha", "/sorry/", "unusual traffic",
    "not a robot", "captcha-form", "www.google.com/recaptcha",
)


# True when a Scholar 200 body is actually an antibot wall, not a result page.
def is_scholar_block(html_text: str) -> bool:
    low = (html_text or "").lower()
    if any(m in low for m in _SCHOLAR_BLOCK_MARKERS):
        return True
    # A genuine result page always carries the result container; its absence on a
    # non-trivial body means we were served something other than results.
    return "gs_r" not in low and len(low) > 2000


def parse_scholar(html_text: str) -> list[AcademicPaper]:
    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(html_text or "", "lxml")
    except Exception:  # noqa: BLE001 — never let a parser backend hiccup sink the provider
        return []
    out: list[AcademicPaper] = []
    for ri in soup.select("div.gs_ri"):
        block = ri.find_parent("div", class_="gs_r") or ri
        title_el = ri.select_one("h3.gs_rt")
        if title_el is None:
            continue
        link = title_el.select_one("a")
        title = _clean(title_el.get_text(" "))
        # Strip leading "[PDF]", "[BOOK]", "[CITATION]" tags Scholar prefixes onto titles.
        title = re.sub(r"^\[[A-Z]+\]\s*", "", title)
        meta = _clean((ri.select_one("div.gs_a") or _Empty()).get_text(" "))
        year_m = _YEAR_IN_META_RE.search(meta)
        authors = [a.strip() for a in meta.split(" - ")[0].split(",") if a.strip()]
        cited = ""
        for a in ri.select("div.gs_fl a"):
            if "cited by" in a.get_text(" ").lower():
                cited = a.get_text(" ")
                break
        cm = _CITED_BY_RE.search(cited)
        pdf = ""
        ggs = block.select_one("div.gs_ggs a") if block is not ri else None
        if ggs and ggs.get("href"):
            pdf = str(ggs["href"])  # right-hand "[PDF] domain" link, on the parent block
        url = str(link["href"]) if link and link.get("href") else ""
        out.append(AcademicPaper(
            id=url or title,
            title=title,
            url=url,
            source="scholar",
            source_domain="scholar.google.com",
            authors=authors[:8],
            abstract=_abstract((ri.select_one("div.gs_rs") or _Empty()).get_text(" ")),
            year=_int(year_m.group(0)) if year_m else None,
            pdf_url=pdf,
            citations=_int(cm.group(1).replace(",", "")) if cm else None,
        ))
    return out


# Tiny null-object so a missing optional element can still be .get_text()'d.
class _Empty:
    def get_text(self, *_a, **_k) -> str:
        return ""


# SerpApi google_scholar engine: block-free Scholar (SerpApi solves the antibot on their
# backend), returned as clean JSON. Same fields as a scrape, but reliable and key-gated.
def parse_serpapi_scholar(body: dict[str, Any]) -> list[AcademicPaper]:
    out: list[AcademicPaper] = []
    for it in body.get("organic_results", []) or []:
        if not isinstance(it, dict):
            continue
        pub = it.get("publication_info") or {}
        summary = str(pub.get("summary") or "")
        authors = [
            str(a.get("name") or "") for a in pub.get("authors", []) or [] if isinstance(a, dict)
        ]
        if not authors and summary:
            authors = [a.strip() for a in summary.split(" - ")[0].split(",") if a.strip()]
        year_m = _YEAR_IN_META_RE.search(summary)
        cited = ((it.get("inline_links") or {}).get("cited_by") or {}).get("total")
        pdf = ""
        for res in it.get("resources", []) or []:
            if isinstance(res, dict) and str(res.get("file_format") or "").upper() == "PDF":
                pdf = str(res.get("link") or "")
                break
        out.append(AcademicPaper(
            id=str(it.get("result_id") or it.get("link") or it.get("title")),
            title=_clean(it.get("title") or ""),
            url=str(it.get("link") or ""),
            source="scholar",
            source_domain="scholar.google.com",
            authors=[a for a in authors[:8] if a],
            abstract=_abstract(it.get("snippet") or ""),
            year=_int(year_m.group(0)) if year_m else None,
            pdf_url=pdf,
            citations=_int(cited),
            meta={"via": "serpapi"},
        ))
    return out


PARSERS = {
    "openalex": parse_openalex,
    "crossref": parse_crossref,
    "europepmc": parse_europepmc,
    "doaj": parse_doaj,
}
