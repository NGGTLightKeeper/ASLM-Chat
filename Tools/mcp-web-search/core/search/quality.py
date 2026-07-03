# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Model-free SERP quality signals.

Everything here is deterministic, allocation-light, and budgeted for sub-millisecond
per-source evaluation so triage can run inline with the live result stream.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from core.extract.scoring import query_terms

# --- lexical -----------------------------------------------------------------

_WORD_CACHE_MAX = 256
_pattern_cache: dict[str, re.Pattern[str]] = {}


# Compile a word-boundary pattern for a term ("rust" must not match "trust").
# Terms with non-word edges (e.g. "c++") are already normalized away by
# query_terms, so plain \b is sufficient here.
def _term_pattern(term: str) -> re.Pattern[str]:
    pattern = _pattern_cache.get(term)
    if pattern is None:
        if len(_pattern_cache) >= _WORD_CACHE_MAX:
            _pattern_cache.clear()
        pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        _pattern_cache[term] = pattern
    return pattern


# BM25-lite relevance in [0,1] over title/snippet/URL path with word-boundary
# matching. Same shape as core.extract.scoring.lexical_score, minus its substring
# false-positives ("java" in "javascript").
def lexical_score(query: str, title: str, snippet: str, url: str) -> float:
    terms = query_terms(query)
    if not terms:
        return 0.0
    url_path = (urlparse(url).path or "").replace("-", " ").replace("_", " ").replace("/", " ")
    n = len(terms)
    title_hits = sum(1 for t in terms if _term_pattern(t).search(title))
    snippet_hits = sum(1 for t in terms if _term_pattern(t).search(snippet))
    path_hits = sum(1 for t in terms if _term_pattern(t).search(url_path))
    return min(1.0, 0.6 * title_hits / n + 0.3 * snippet_hits / n + 0.1 * path_hits / n)


# --- hub / garbage detection ---------------------------------------------------

_HUB_URL_SEGMENTS = frozenset({
    "category", "categories", "tag", "tags", "topic", "topics",
    "theme", "themes", "rubric", "rubrics", "section", "sections",
    "label", "labels", "archive", "archives", "feed", "rss",
    "search", "results", "page", "index", "catalog",
})
_HUB_TITLE_PHRASES = (
    "all news", "all articles", "all posts", "news feed", "tag page",
    "category page", "topic page", "browse", "archive",
    "все новости", "последние новости", "все статьи",
)
_SKIP_TITLE_PATTERNS = frozenset({
    "login", "log in", "sign up", "signup", "sign in", "register",
    "create account", "subscribe", "404", "403", "not found",
    "access denied", "page not found", "permission denied",
})


# Penalty in [0,1] for hub/listing pages that parse into link soup, not content.
def hub_penalty(url: str, title: str, snippet: str) -> float:
    penalty = 0.0
    path = (urlparse(url).path or "").lower().strip("/")
    if set(path.split("/")) & _HUB_URL_SEGMENTS:
        penalty += 0.5
    if not path or path in {"index", "index.html", "index.php"}:
        penalty += 0.3
    title_l = (title or "").lower()
    if any(phrase in title_l for phrase in _HUB_TITLE_PHRASES):
        penalty += 0.4
    snippet = snippet or ""
    if snippet.count(" | ") >= 4 or snippet.count(" · ") >= 3 or snippet.count(" • ") >= 3:
        penalty += 0.25
    return min(penalty, 1.0)


# True for titles that scream non-content (login walls, error pages).
def is_skip_title(title: str) -> bool:
    title_l = (title or "").lower()
    return any(pattern in title_l for pattern in _SKIP_TITLE_PATTERNS)


# --- SEO-slug penalty (identity-blind) -----------------------------------------

# No domain favouritism: the ranker must not carry a list of "good" hosts — that would
# reintroduce the curated trust registry consensus was built to replace, and bias the
# system toward whoever the author hand-picked. The only domain-shaped signal we allow
# is a penalty on the *structure* of a URL, never on its identity: year-stuffed,
# heavily hyphenated slugs are a reliable SEO-content-farm tell regardless of who owns
# the domain. Authority itself comes from cross-engine consensus (see triage), which is
# earned from the live result stream, not declared here.

_SEO_SLUG_RE = re.compile(r"\b(19|20)\d{2}\b")


# Non-positive penalty for SEO-farm-shaped slugs. Identity-blind: keys only off the URL
# slug's shape (hyphen density + a year), so it generalises to any host and plays no
# favourites. Deliberately gentle — it nudges, never filters.
def seo_slug_penalty(url: str) -> float:
    last = (urlparse(url).path or "").rstrip("/").rsplit("/", 1)[-1].lower()
    if last.count("-") >= 6 and _SEO_SLUG_RE.search(last):
        return -0.06
    return 0.0


# --- TLD tiers & transport security (identity-blind, structural) ----------------

# IMPORTANT DISTINGUISHING SIGNAL — the TLD tier.
# The TLD a domain sits under is a cheap, identity-blind proxy for one hard-to-fake fact:
# was this zone reachable BEFORE the era when a throwaway domain cost a dollar? The line
# is drawn at ICANN's 2012 new-gTLD program, not at anyone's taste. Everything a
# registrant could obtain before that expansion — the pre-2012 gTLDs below, plus every
# ccTLD (two-letter, or an IDN ccTLD in xn--* punycode) — is "established": it earns a
# NEUTRAL prior, never a bonus. Everything the expansion minted (.dev/.xyz/.top/.online/…)
# is "unproven": also never penalised by name — that would rebuild the curated trust
# registry consensus was built to delete — but held to a slightly stricter parse bar
# until the domain earns positive history in the runtime reputation store.
#
# Why this is the right axis and not a blocklist: content farms and phishing kits cluster
# on the cheapest, most permissive new gTLDs precisely because identity there is
# disposable; a .com/.co.uk carries no such prior either way, so we neither reward nor
# punish it. The tier only decides how much proof we ask of a stranger, never whether it
# is "good" or "bad" — that verdict is always earned downstream (consensus + reputation).
#
# Completeness (verified 2026-07 against ICANN/Wikipedia): this is the FULL pre-2012 set —
# 1985 RFC-920 originals (com/edu/gov/mil/org/net) + int (1988) + arpa (infrastructure),
# the 2000 round (aero/biz/coop/info/museum/name/pro), the 2003–04 sponsored round
# (asia/cat/jobs/mobi/tel/travel), xxx (2011) and post (UPU, 2012). Anything not here
# is expansion-era by construction, so the frozenset never needs growing — new gTLDs are
# supposed to fall through to the unproven tier.
_LEGACY_GTLDS = frozenset({
    "com", "net", "org", "edu", "gov", "mil", "int", "arpa",
    "info", "biz", "name", "pro", "aero", "asia", "cat", "coop",
    "jobs", "mobi", "museum", "post", "tel", "travel", "xxx",
})


# True when a host sits under an established TLD (legacy gTLD or any ccTLD). ccTLDs pass
# on the two-letter rule, so multi-label suffixes (.co.uk, .com.br) qualify via their
# real TLD (.uk/.br) with no separate suffix list to maintain.
def is_established_tld(host_or_domain: str) -> bool:
    tld = (host_or_domain or "").lower().rstrip(".").rsplit(".", 1)[-1]
    return len(tld) == 2 or tld.startswith("xn--") or tld in _LEGACY_GTLDS


# Non-positive penalty for plain-http SERP URLs — the only transport-security signal
# available with zero I/O at triage time. Gentle: legitimate old mirrors still exist.
def insecure_scheme_penalty(url: str) -> float:
    return -0.08 if (url or "").lower().startswith("http://") else 0.0


# --- bad-site tells (identity-blind, zero-I/O) -----------------------------------
# Structural marks that phishing/farm sites wear and legitimate sites rarely do. Same
# contract as seo_slug_penalty: shape only, never names; each tell is gentle and the
# pack is capped so stacked tells demote a source, never execute it — SKIP still comes
# only from irrelevance, and consensus votes can outweigh the whole pack.

_SUSPICIOUS_PACK_CAP = 0.20
_IP_HOST_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_DOMAIN_YEAR_RE = re.compile(r"(?:19|20)\d{2}")


# Combined non-positive penalty for structural unsafe-site tells in a SERP URL.
def suspicious_url_penalty(url: str) -> float:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        return -_SUSPICIOUS_PACK_CAP  # unparseable URL is its own tell
    if not host:
        return 0.0
    penalty = 0.0

    # IP-literal host: organic results virtually never point at bare addresses.
    if _IP_HOST_RE.fullmatch(host) or host.startswith("["):
        penalty += 0.15
    # Explicit non-default port — SERP-worthy content does not live on :8080.
    if port not in (None, 80, 443):
        penalty += 0.12

    labels = host.split(".")
    # A gTLD-shaped label buried in the subdomain chain ("github.com.evil.xyz") is a
    # phishing costume. labels[:-2] keeps ccTLD second-level registries (example.com.br,
    # example.co.uk) out of the blast radius.
    if any(label in _LEGACY_GTLDS for label in labels[:-2]):
        penalty += 0.15
    # Hyphen-dense or year-stamped domain labels: the registered-name cousins of the
    # SEO slug tell ("best-ai-coding-tools-2026.com", "top10vpn2024.net"). Deliberately
    # feather-light: name shape correlates with farms but convicts nobody, and stacking
    # heavier name penalties would just monopolise the SERP for incumbent big domains.
    # Safety tells above (IP/port/costume) stay stronger — those are about deception,
    # not taste in naming.
    if any(label.count("-") >= 3 for label in labels[:-1]):
        penalty += 0.04
    if any(_DOMAIN_YEAR_RE.search(label) for label in labels[:-1]):
        penalty += 0.03

    return -min(penalty, _SUSPICIOUS_PACK_CAP)


# Exact-match-domain tell (Google EMD-update heritage): a registered name that IS the
# query ("claudecode.pro" for "claude code") is usually a squatter riding the phrase,
# not the subject itself. Deliberately the gentlest tell — legitimate exact-match
# domains exist, and they can win the margin back with one consensus vote. Kept at a
# whisper (-0.03) by explicit policy: name-shape penalties must nudge the margin, not
# gate the market for established domains.
def emd_penalty(url: str, terms: tuple[str, ...] | list[str]) -> float:
    if len(terms) < 2:
        return 0.0
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return 0.0
    labels = host.removeprefix("www.").split(".")
    if len(labels) < 2:
        return 0.0
    name = labels[0].replace("-", "")
    if len(name) < 6:
        return 0.0
    # The registered name must be fully spelled by ≥2 consecutive query terms.
    for start in range(len(terms) - 1):
        candidate = terms[start]
        for term in terms[start + 1:]:
            candidate += term
            if len(candidate) > len(name):
                break
            if candidate == name:
                return -0.03
    return 0.0


# --- dates (policy: soft signal only, never a hard filter) ---------------------

_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
_DATE_SIGNAL_RE = re.compile(
    r"\b(20\d{2}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
    re.IGNORECASE,
)


# Years the caller explicitly wrote into the query. Only these may influence
# scoring — hard date limits are forbidden by policy (they cut good content).
def query_years(query: str) -> list[str]:
    return _YEAR_RE.findall(query or "")


# Soft year alignment: +1 when source text mentions a queried year, small negative
# when it carries other years only, 0 when it has no year signal at all.
def year_match_score(text: str, years: list[str]) -> float:
    if not years or not text:
        return 0.0
    found = set(_YEAR_RE.findall(text))
    if not found:
        return 0.0
    return 1.0 if set(years) & found else -0.3


# True when a snippet carries any date marker (slight freshness/context signal).
def has_date_signal(snippet: str) -> bool:
    return bool(_DATE_SIGNAL_RE.search(snippet or ""))


# --- query language (legacy port: services/web_search.py::infer_query_language) -

# Unicode-block counters; ≥15% of characters in-script qualifies the language.
_SCRIPT_RANGES: tuple[tuple[str, int, int], ...] = (
    ("ru", 0x0400, 0x04FF),  # Cyrillic
    ("ar", 0x0600, 0x06FF),  # Arabic
    ("he", 0x0590, 0x05FF),  # Hebrew
    ("ja", 0x3040, 0x30FF),  # Hiragana/Katakana (unambiguous Japanese)
    ("zh", 0x4E00, 0x9FFF),  # CJK Unified (zh unless Japanese kana present)
    ("ko", 0xAC00, 0xD7AF),  # Hangul
    ("th", 0x0E00, 0x0E7F),  # Thai
    ("hi", 0x0900, 0x097F),  # Devanagari
    ("el", 0x0370, 0x03FF),  # Greek
)


# Detect the dominant script of a query → 2-letter language code (default "en").
# Used to route region/language per engine (e.g. Yandex for Cyrillic queries).
def infer_query_language(query: str) -> str:
    text = str(query or "")
    if not text:
        return "en"
    threshold = max(1, len(text)) * 0.15
    counts = {lang: 0 for lang, _, _ in _SCRIPT_RANGES}
    for ch in text:
        cp = ord(ch)
        for lang, lo, hi in _SCRIPT_RANGES:
            if lo <= cp <= hi:
                counts[lang] += 1
                break
    if counts["ja"] > 0:
        counts["zh"] = 0  # kana present → the CJK block is Japanese, not Chinese
    for lang, _, _ in _SCRIPT_RANGES:
        if counts[lang] >= threshold:
            return lang
    return "en"
