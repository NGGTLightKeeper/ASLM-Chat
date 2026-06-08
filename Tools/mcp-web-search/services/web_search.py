# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import contextlib
from contextlib import contextmanager
import html as html_lib
import json
import logging
import os
import re
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from core.models.search import SearchResult, SearchRichResult, SearchSource
from core.config import load_search_config
from core.fetch.ddgs_client import async_ddgs_search
from core.fetch.shopping.worker import async_shopping_search_worker
from core.fetch.academic_fetcher import AcademicFetcher
from core.fetch.hosted_clients import async_hosted_search, available_hosted_engines
from core.query import (
    build_provider_query,
    filter_results_by_domain_constraints,
    infer_query_types_hybrid,
    infer_query_types_from_rules,
    journalistic_intent_terms,
    parse_domain_constraints,
    score_query_against_profiles,
)
from core.query.aslm_embedding_runtime import SearchModelSession
from core.query.routing_score import (
    QueryClassWeight,
    allocate_source_budget,
    compute_routing_score,
    ensure_general_fallback,
    normalize_class_mix,
)
from core.extract.content_processor import (
    build_preview_payload, get_preview_settings, warm_preview_models, PreviewPayload,
)
from core.extract.page_normalizer import normalize_page
from core.registry.trust_registry import get_trust_registry
from core.registry.domain_reputation import get_reputation_store, domain_from_url
from core.registry.domain_registry import get_registry
from core.fetch.antibot import is_antibot
from core.fetch.stackexchange_fetcher import fetch_stackexchange_question, is_stackexchange_question_url
from custom_domains.github import fetch_github_page, is_github_url
from core.fetch.url_utils import (
    UnsafeFetchUrl,
    max_safe_redirects,
    normalize_url,
    validate_public_fetch_url,
    validate_redirect_target,
)
from core.fetch.thread_pool import io_pool as _io_pool
from core.cache.source_cache import SourceCache
from core.cache.query_normalizer import QUERY_STOPWORDS as _QUERY_STOPWORDS
from core.extract.pdf_extractor import looks_like_pdf_url, looks_like_pdf_bytes, pdf_bytes_to_markdown
from core.extract.scoring import (
    densify_text_gliner as _densify_text_gliner,
    lexical_score as _lexical_score,
    query_terms as _query_terms_from_scoring,
)

# PDF preview limits — tighter than read_page (10 MB) since this is just a preview
_PDF_PREVIEW_MAX_BYTES = 5 * 1024 * 1024   # 5 MB download cap
_PDF_PREVIEW_MAX_CHARS = 40_000             # raw extract cap before GliNER
_PDF_PREVIEW_OUTPUT_CHARS = 3_000          # densified output target

_CACHE_PATH = Path(__file__).resolve().parent.parent / "_cache" / "source_cache.db"
_cache = SourceCache(str(_CACHE_PATH))


# True for HTTP redirect status codes.
def _is_redirect_status(status_code: int) -> bool:
    return status_code in {301, 302, 303, 307, 308}

# Persistent HTTP connector — reused across preview-fetch batches to avoid
# rebuilding connection pools on every search call.
_http_connector: Optional["aiohttp.TCPConnector"] = None  # type: ignore[name-defined]


# Return (or lazily create) the shared TCPConnector for preview fetches.
async def _get_http_connector(concurrency: int) -> "aiohttp.TCPConnector":  # type: ignore[name-defined]
    global _http_connector
    import aiohttp as _aiohttp
    if _http_connector is None or _http_connector.closed:
        _http_connector = _aiohttp.TCPConnector(
            limit=concurrency * 4, limit_per_host=2, ttl_dns_cache=120
        )
    return _http_connector


# Close shared HTTP connector on MCP server shutdown.
async def shutdown_web_search() -> None:
    global _http_connector
    if _http_connector is not None and not _http_connector.closed:
        await _http_connector.close()
        _http_connector = None


# aiohttp text fetch with per-redirect SSRF checks.
async def _aiohttp_get_text_checked(
    session,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    content_tokens: tuple[str, ...] = ("html", "xml", "text"),
) -> str | None:
    current_url = validate_public_fetch_url(url)
    for _ in range(max_safe_redirects() + 1):
        async with session.get(current_url, allow_redirects=False, headers=headers) as resp:
            if _is_redirect_status(resp.status):
                current_url = validate_redirect_target(current_url, resp.headers.get("location", ""))
                continue
            if resp.status >= 400:
                return None
            content_type = (resp.headers.get("Content-Type") or "").lower()
            if content_type and all(token not in content_type for token in content_tokens):
                return None
            return await resp.text(errors="replace")
    return None


# curl_cffi text fetch with per-redirect SSRF checks.
def _curl_get_text_checked(
    url: str,
    *,
    timeout: int,
    headers: dict[str, str],
    content_tokens: tuple[str, ...] = ("html", "xml", "text"),
) -> str | None:
    from curl_cffi import requests as cffi_req

    current_url = validate_public_fetch_url(url)
    for _ in range(max_safe_redirects() + 1):
        r = cffi_req.get(
            current_url,
            impersonate="chrome124",
            timeout=timeout,
            headers=headers,
            allow_redirects=False,
        )
        if _is_redirect_status(int(r.status_code)):
            current_url = validate_redirect_target(current_url, r.headers.get("location", ""))
            continue
        if r.status_code >= 400:
            return None
        content_type = (r.headers.get("Content-Type") or r.headers.get("content-type") or "").lower()
        if content_type and all(token not in content_type for token in content_tokens):
            return None
        return r.text
    return None
logger = logging.getLogger("services.web_search")
trace_logger = logging.getLogger("trace.web_search")

_SEARCH_EFFORT_VALUES = {"low", "medium", "high"}
_SEARCH_EFFORT_ALIASES = {
    "": "medium",
    "normal": "medium",
    "default": "medium",
    "standard": "medium",
}


# Generate a short hex request id for trace logs.
def _make_request_id() -> str:
    return secrets.token_hex(4)


# Emit a structured trace line for web_search stages.
def _trace(req_id: str, stage: str, **fields: object) -> None:
    extras = " ".join(f"{key}={value!r}" for key, value in fields.items())
    message = f"req={req_id} stage={stage}"
    if extras:
        message = f"{message} {extras}"
    trace_logger.info(message)


# Maps human-readable aliases to DDGS timelimit values (d/w/m/y).
_TIME_RANGE_MAP: dict[str, str] = {
    # DDGS native (pass-through)
    "d": "d", "w": "w", "m": "m", "y": "y",
    # English aliases
    "day": "d", "today": "d",
    "week": "w", "last_week": "w",
    "month": "m", "last_month": "m",
    "year": "y", "last_year": "y",
    # Short shorthands
    "1d": "d", "7d": "w", "30d": "m", "365d": "y",
}


# Map a human-readable time range alias to a DDGS timelimit (d/w/m/y).
def _normalize_time_range(time_range: Optional[str]) -> Optional[str]:
    if not time_range:
        return None
    return _TIME_RANGE_MAP.get(time_range.strip().lower().replace("-", "_"))


# Maps primary query type → DDGS timelimit.
# Rationale:
#   journalistic / finance  — events and prices go stale in weeks; cap at month
#   shopping / troubleshoot / forum / technical — relevant within the last year
#   academic / medical / general — timeless or unknown; no restriction
_AUTO_TIMELIMIT: dict[str, Optional[str]] = {
    "journalistic":   "m",   # news articles — last month
    "finance":        "m",   # market / pricing — last month
    "shopping":       "y",   # products change within a year
    "troubleshooting":"y",   # fixes are usually still valid within a year
    "forum":          "y",   # discussions — within a year
    "technical":      "y",   # docs — within a year (version-specific)
    "academic":       None,  # research papers — no cutoff
    "medical":        None,  # clinical studies — no cutoff
    "general":        None,  # unknown intent — don't restrict
}


# Infer DDGS timelimit from primary classified query type.
def _auto_timelimit(query_types: list[str]) -> Optional[str]:
    primary = query_types[0] if query_types else "general"
    return _AUTO_TIMELIMIT.get(primary, None)


# Ordering for timelimit values — smaller index = tighter (more restrictive) window.
_TIMELIMIT_ORDER: dict[str, int] = {"d": 0, "w": 1, "m": 2, "y": 3}


# Return the more restrictive of two timelimits (None = no restriction).
def _stricter_timelimit(a: Optional[str], b: Optional[str]) -> Optional[str]:
    if a is None:
        return b
    if b is None:
        return a
    return a if _TIMELIMIT_ORDER.get(a, 99) <= _TIMELIMIT_ORDER.get(b, 99) else b


# True when the query anchors to a year before last calendar year.
def _has_historical_year_anchor(query: str) -> bool:
    raw_years = re.findall(r'\b((?:19|20)\d{2})\b', query or "")
    if not raw_years:
        return False

    import datetime as _dt
    this_year = _dt.date.today().year
    return min(int(year) for year in raw_years) < this_year - 1


# Combine query-type auto timelimit with historical-year override.
def _resolve_auto_timelimit(query: str) -> Optional[str]:
    if _has_historical_year_anchor(query):
        return None
    return _auto_timelimit(infer_query_types(query))


# Map trailing year tokens in the query to a DDGS timelimit when mode is timelimit.
def _year_hint_timelimit(
    query: str,
    mode: str,
    current: Optional[str],
    prev: Optional[str],
    older: Optional[str],
) -> Optional[str]:
    if (mode or "").strip().lower() != "timelimit":
        return None

    lower = query.lower()
    has_freshness = any(hint in lower for hint in _TRAILING_YEAR_FRESHNESS_HINTS)
    has_comma_year = bool(_TRAILING_YEAR_COMMA_RE.search(query))
    if not has_freshness and not has_comma_year:
        return None

    raw_years = re.findall(r'\b((?:19|20)\d{2})\b', query)
    if not raw_years:
        return None

    import datetime as _dt
    this_year = _dt.date.today().year
    year = max(int(y) for y in raw_years)

    if year >= this_year:
        return current
    elif year == this_year - 1:
        return prev
    else:
        return older


# Apply year_hint_mode: strip years and/or derive timelimit from config.
def _apply_year_hint_policy(query: str, qcfg: object) -> tuple[str, Optional[str]]:
    mode = str(getattr(qcfg, "year_hint_mode", "timelimit") or "timelimit").strip().lower()
    if mode not in {"timelimit", "strip", "none"}:
        mode = "timelimit"

    year_tl = _year_hint_timelimit(
        query,
        mode=mode,
        current=getattr(qcfg, "year_hint_current", "m"),
        prev=getattr(qcfg, "year_hint_prev", "y"),
        older=getattr(qcfg, "year_hint_older", None),
    )
    if mode == "none":
        return query, None
    return _strip_trailing_year(query), year_tl


# Comma-preceded trailing year: always a time-tag, never a topic anchor.
# Examples: "AI developments, 2023-2024" or "AI developments, 2023 2024".
# Standalone year or year-range anywhere in the query.
# Matches "2025", "2024-2025", "2024 2025", or "2024-2025" with an en dash.
# Does NOT match version numbers like "3.12", "2.0", "GPT-4" - those are
# either decimal (contain a dot) or single-digit, not 4-digit year-shaped.
_YEAR_RANGE_SEPARATOR = r"(?:\s*(?:-|\u2013)\s*|\s+)"
_TRAILING_YEAR_COMMA_RE = re.compile(
    rf",\s+(?:(?:19|20)\d{{2}})(?:{_YEAR_RANGE_SEPARATOR}(?:19|20)\d{{2}})?\s*$"
)
_YEAR_ANYWHERE_RE = re.compile(
    rf"\b(?:19|20)\d{{2}}(?:{_YEAR_RANGE_SEPARATOR}(?:19|20)\d{{2}})?\b"
)
# Words that signal any year in the query is a freshness hint, not a topic anchor.
_TRAILING_YEAR_FRESHNESS_HINTS: frozenset[str] = frozenset({
    "latest", "recent", "current", "now", "today", "yesterday",
    "update", "updates", "news", "breaking", "headline",
    # Russian / Ukrainian
    "новости", "последние", "сейчас", "сегодня", "новини", "зараз", "сьогодні",
    # German / French / Dutch
    "aktuell", "neueste", "récent", "actuels", "laatste",
})


# Strip year tokens used as freshness hints (comma-trailing or with freshness words).
def _strip_trailing_year(query: str) -> str:
    # Case 1: comma-separated trailing year → unconditional strip
    if _TRAILING_YEAR_COMMA_RE.search(query):
        cleaned = _TRAILING_YEAR_COMMA_RE.sub("", query).strip()
        return cleaned if cleaned else query

    # Case 2: freshness hint → strip all standalone years anywhere
    lower = query.lower()
    if any(hint in lower for hint in _TRAILING_YEAR_FRESHNESS_HINTS):
        cleaned = _YEAR_ANYWHERE_RE.sub("", query)
        cleaned = " ".join(cleaned.split())   # collapse extra spaces
        return cleaned if cleaned.strip() else query

    return query



# Query quality gate — SEO spam words & word-count ceiling

#: Words that signal an SEO/clickbait-style query rather than a focused search
#: expression.  This list intentionally stays narrow: ordinary research intents
#: such as reviews, comparisons, rankings, and how-to lookups are allowed when
#: paired with specific nouns or identifiers.
_SEO_SPAM_WORDS: frozenset[str] = frozenset({
    # ── English ──────────────────────────────────────────────────────────────
    "best", "top", "ultimate", "amazing", "awesome", "incredible",
    "most popular", "highly rated", "top-rated", "top rated", "number one",
    "#1", "must-have", "must have", "must-know", "must know",
    "comprehensive", "complete guide", "definitive", "essential",
    "everything you need", "all you need", "you need to know",
    # ── Russian / Ukrainian ──────────────────────────────────────────────────
    "лучший", "лучшая", "лучшее", "лучшие",
    "топ", "топовый", "топовая", "самый популярный", "самая популярная", "всё что нужно",
    "полное руководство", "подробный гайд", "обязательно знать",
    "найлучший", "найкращий", "найкраща", "найкраще", "найкращі",
    "топ", "повний посібник",
    # ── German / Dutch ───────────────────────────────────────────────────────
    "beste", "bester", "bestes", "besten", "top", "beliebteste",
    "testsieger", "vollständiger leitfaden", "ultimativ",
    "beste", "best", "top", "complete gids",
    # ── Nordic ───────────────────────────────────────────────────────────────
    "bästa", "bäst", "topp", "populäraste", "komplett guide",
    "bedste", "top", "komplet guide",
    "paras", "parhaat", "täydellinen opas",
    "beste", "best", "topp", "komplett guide",
    # ── French ───────────────────────────────────────────────────────────────
    "meilleur", "meilleure", "meilleurs", "meilleures",
    "top", "plus populaire", "guide complet", "guide ultime",
    # ── Spanish / Portuguese ─────────────────────────────────────────────────
    "mejor", "mejores", "top", "más popular", "guía completa", "guía definitiva",
    "melhor", "melhores", "top", "mais popular", "guia completo", "guia definitivo",
    # ── Italian ──────────────────────────────────────────────────────────────
    "migliore", "migliori", "top", "più popolare", "guida completa", "guida definitiva",
    # ── Central / Eastern European ───────────────────────────────────────────
    "najlepszy", "najlepsza", "najlepsze", "najlepsi", "top",
    "najpopularniejszy", "kompletny przewodnik",
    "nejlepší", "top", "nejoblíbenější", "kompletní průvodce",
    "najlepší", "top", "najpopulárnejší", "kompletný sprievodca",
    "legjobb", "top", "legnépszerűbb", "teljes útmutató",
    "cel mai bun", "cele mai bune", "top", "ghid complet",
    "най-добър", "най-добра", "най-добро", "най-добри", "топ",
    "пълно ръководство",
    "најбољи", "најбоља", "најбоље", "топ",
    "najbolji", "najbolja", "najbolje",
    # ── Turkish ──────────────────────────────────────────────────────────────
    "en iyi", "top", "en popüler", "tam rehber",
    # ── Arabic / Hebrew / Persian ────────────────────────────────────────────
    "أفضل", "الأفضل", "الأكثر شعبية", "دليل شامل",
    "הטוב ביותר", "הטובים ביותר", "הכי פופולרי", "מדריך מלא",
    "بهترین", "برترین", "محبوب‌ترین", "راهنمای کامل",
    "بہترین", "مقبول ترین", "مکمل رہنما",
    # ── Chinese / Japanese / Korean ──────────────────────────────────────────
    "最好", "最佳", "最受欢迎", "全面指南", "终极指南",
    "最高", "ベスト", "完全ガイド", "究極ガイド",
    "최고", "최상", "가장 인기", "완전 가이드",
    # ── South Asian ──────────────────────────────────────────────────────────
    "सबसे अच्छा", "बेहतरीन", "सबसे लोकप्रिय", "पूरी गाइड",
    "সেরা", "সবচেয়ে জনপ্রিয়", "সম্পূর্ণ গাইড",
    "சிறந்த", "மிகவும் பிரபலமான", "முழு வழிகாட்டி",
    "ఉత్తమ", "అత్యంత ప్రజాదరణ", "పూర్తి గైడ్",
    "ਸਭ ਤੋਂ ਵਧੀਆ", "ਪੂਰੀ ਗਾਈਡ",
    # ── Southeast Asian ──────────────────────────────────────────────────────
    "terbaik", "paling populer", "panduan lengkap",
    "tốt nhất", "phổ biến nhất", "hướng dẫn đầy đủ",
    "ดีที่สุด",
    "ល្អបំផុត", "ពេញនិយមបំផុត", "មគ្គុទ្ទេសក៍ពេញលេញ",
    "အကောင်းဆုံး", "လူကြိုက်အများဆုံး", "လမ်းညွှန်အပြည့်အစုံ",
    # ── Greek ────────────────────────────────────────────────────────────────
    "καλύτερο", "καλύτερη", "καλύτερα", "κορυφαίο",
    "πιο δημοφιλές", "πλήρης οδηγός",
})

_NATURAL_INTENT_WORDS: frozenset[str] = frozenset({
    # Keep ordinary informational/comparison intents searchable.  These words
    # can appear in SEO spam, but on their own they are valid focused queries.
    "how to", "what is", "what are", "why is", "why are",
    "review", "reviews", "reviewed", "comparison", "compared", "versus", "vs",
    "rated", "ranked", "ranking", "rankings", "popular",
    "обзор", "обзоры", "сравнение", "как выбрать", "что такое", "зачем нужен",
    "рейтинг", "рейтинги", "популярный", "популярная",
    "огляд", "огляди", "порівняння", "що таке", "популярний", "популярна",
    "bewertung", "bewertungen", "vergleich", "empfehlung", "wie man", "was ist",
    "beliebt", "beoordeling", "beoordelingen", "vergelijking", "aanbeveling",
    "populair", "wat is",
    "populär", "rankning", "jämförelse", "recension", "recensioner", "vad är",
    "populær", "rangering", "sammenligning", "anmeldelse", "anmeldelser", "hvad er",
    "suosituin", "sijoitus", "vertailu", "arvostelu", "arvostelut", "mikä on",
    "hva er",
    "populaire", "classement", "comparatif", "avis", "critique", "comment", "qu'est-ce que",
    "popular", "clasificación", "ranking", "comparativa", "comparación", "reseña", "reseñas",
    "cómo", "qué es", "classificação", "comparação", "análise", "avaliação", "como", "o que é",
    "popolare", "classifica", "confronto", "comparazione", "recensione", "recensioni",
    "come", "che cos'è",
    "popularny", "porównanie", "recenzja", "recenzje", "jak", "co to jest",
    "žebříček", "srovnání", "recenze", "co je",
    "rebríček", "porovnanie", "recenzia", "recenzie", "čo je",
    "népszerű", "rangsor", "összehasonlítás", "értékelés", "vélemény", "mi az",
    "clasament", "comparație", "recenzie", "recenzii", "ce este",
    "популярен", "класация", "сравнение", "ревю", "отзив",
    "рангирање", "поређење", "рецензија", "ljestvica", "usporedba", "recenzija",
    "popüler", "sıralama", "karşılaştırma", "inceleme", "yorum", "nasıl", "nedir",
    "تقييم", "تصنيف", "ترتيب", "مقارنة", "مراجعة", "مراجعات", "ما هو",
    "דירוג", "השוואה", "ביקורת", "ביקורות", "מה זה",
    "رتبه‌بندی", "رده‌بندی", "مقایسه", "بررسی", "نقد", "چیست",
    "درجہ بندی", "موازنہ", "جائزہ", "کیا ہے",
    "热门", "排名", "排行榜", "比较", "对比", "评测", "测评", "评价", "如何", "什么是",
    "人気", "ランキング", "比較", "レビュー", "口コミ", "評価", "方法", "とは",
    "인기", "랭킹", "순위", "비교", "리뷰", "후기", "평가", "방법", "이란",
    "लोकप्रिय", "रैंकिंग", "तुलना", "समीक्षा", "क्या है",
    "শীর্ষ", "র‍্যাঙ্কিং", "তুলনা", "রিভিউ", "পর্যালোচনা", "কি",
    "தரவரிசை", "ஒப்பீடு", "விமர்சனம்",
    "ర్యాంకింగ్", "పోలిక", "సమీక్ష",
    "ਪ੍ਰਸਿੱਧ", "ਰੈਂਕਿੰਗ", "ਤੁਲਨਾ", "ਸਮੀਖਿਆ",
    "peringkat", "perbandingan", "ulasan", "apa itu",
    "xếp hạng", "so sánh", "đánh giá", "là gì",
    "ยอดนิยม", "อันดับ", "เปรียบเทียบ", "รีวิว", "คืออะไร",
    "ចំណាត់ថ្នាក់", "ប្រៀបធៀប", "ពិនិត្យ",
    "အဆင့်", "နှိုင်းယှဉ်", "သုံးသပ်ချက်",
    "δημοφιλές", "κατάταξη", "σύγκριση", "αξιολόγηση", "κριτική", "τι είναι",
})
_SEO_SPAM_WORDS = frozenset(word for word in _SEO_SPAM_WORDS if word not in _NATURAL_INTENT_WORDS)
_SPACELESS_SCRIPT_RE = re.compile(
    r"[\u0e00-\u0e7f\u1000-\u109f\u1780-\u17ff\u3040-\u30ff\u3400-\u4dbf"
    r"\u4e00-\u9fff\uac00-\ud7af]"
)

#: Hard ceiling for content tokens (non-operator words) in a search query.
#: This should only catch sentence-sized keyword dumps, not ordinary focused
#: technical or academic queries.
_QUERY_MAX_TOKENS: int = 18

#: Regex matching tokens that are search operators, not content words.
#: These are excluded from the word-count ceiling check.
#:
#: Covered patterns (case-insensitive on the lowercased string):
#:   site:foo.com           — include-domain operator
#:   -site:foo.com          — exclude-domain operator
#:   -foo.com               — short exclude alias (leading dash + no space)
#:   +word                  — forced-include prefix
#:   OR / AND / NOT         — boolean connectors
#:   "quoted phrase"        — the entire quoted phrase counts as ONE content token
_OPERATOR_TOKEN_RE = re.compile(
    r"""
    ".*?"                       # quoted phrase  (consume fully; counted separately)
    | -?site:\S+                # site: / -site: operator
    | -[a-z0-9][\w.\-]*\.[a-z]{2,}  # -domain.tld short exclude (-wikipedia.org)
    | \+\S+                     # +forced-include token
    | \bor\b | \band\b | \bnot\b     # boolean connectors
    """,
    re.VERBOSE | re.IGNORECASE,
)


# Count content words in a query (operators and quoted phrases excluded).
def _count_content_tokens(query: str) -> int:
    q = query.strip().lower()

    # Phase 1 — consume and count quoted phrases as single tokens, then remove them.
    quotes = _OPERATOR_TOKEN_RE.findall(q)
    quoted_count = sum(1 for t in quotes if t.startswith('"'))

    # Phase 2 — strip ALL operator tokens (including quoted phrases) from the string.
    remainder = _OPERATOR_TOKEN_RE.sub("", q).strip()

    # Phase 3 — count remaining whitespace-delimited content words.
    content_words = [t for t in remainder.split() if t]
    return len(content_words) + quoted_count


#: The rejection message returned to the model when validation fails.
_QUERY_REJECTION_SPAM: str = (
    "BAD_QUERY: This query contains SEO filler words (e.g. 'best', 'top', "
    "'ultimate', 'amazing', etc.) that reduce search quality. "
    "Please reformulate it keeping only the essential keywords."
)
_QUERY_REJECTION_TOO_LONG: str = (
    f"BAD_QUERY: This query contains more than {_QUERY_MAX_TOKENS} content words "
    f"(search operators like site:, -site:, OR, quoted phrases do not count). "
    f"Web search works best with 1\u2013{_QUERY_MAX_TOKENS} precise keywords. "
    "Please reformulate it keeping only the most specific terms."
)


# True when a banned SEO keyword appears as a whole word or phrase.
def _contains_spam_keyword(query: str, keyword: str) -> bool:
    keyword = str(keyword or "").strip().lower()
    if not keyword:
        return False

    if _SPACELESS_SCRIPT_RE.search(keyword):
        return keyword in query

    if re.search(r"\w", keyword, flags=re.UNICODE):
        return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", query, flags=re.UNICODE) is not None

    # Scripts without word boundaries still need substring matching.
    return keyword in query


# Query text with operators removed, for SEO spam scanning.
def _spam_scan_text(query: str) -> str:
    return _OPERATOR_TOKEN_RE.sub(" ", query.strip().lower()).strip()


# Validate query quality; return None or a BAD_QUERY rejection message.
def validate_search_query(query: str) -> str | None:
    if not query or not query.strip():
        return None  # empty queries are handled elsewhere

    q_lower = _spam_scan_text(query)

    # Check 1: SEO spam words as whole keywords, not substrings.
    spam_hit = {p for p in _SEO_SPAM_WORDS if _contains_spam_keyword(q_lower, p)}
    if spam_hit:
        return _QUERY_REJECTION_SPAM

    # ── Check 2: Content-word ceiling (operators excluded) ────────────────
    if _count_content_tokens(query) > _QUERY_MAX_TOKENS:
        return _QUERY_REJECTION_TOO_LONG

    return None


_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_TEXT_SIG_RE = re.compile(r"[\W_]+", re.UNICODE)

# Triage: title patterns that indicate a non-content page (skip fetch)
_SKIP_TITLE_PATTERNS = frozenset({
    "login", "log in", "sign up", "signup", "sign in", "register",
    "create account", "subscribe", "404", "403", "not found",
    "access denied", "page not found", "permission denied",
})
# Triage: date signal in snippet → slight score boost (content likely has context)
_DATE_SIGNAL_RE = re.compile(
    r"\b(20\d{2}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
    re.IGNORECASE,
)


_query_terms = _query_terms_from_scoring


# Detect dominant script → 2-letter language code for DDGS region routing.
def infer_query_language(query: str) -> str:
    text = str(query or "")
    if not text:
        return "en"

    total = len(text)
    threshold = max(1, total) * 0.15  # ≥15% of chars must be in-script to qualify

    counts: dict[str, int] = {
        "ru": 0,  # Cyrillic
        "ar": 0,  # Arabic
        "he": 0,  # Hebrew
        "ja": 0,  # Hiragana / Katakana (unambiguous Japanese marker)
        "zh": 0,  # CJK Unified (could be zh or ja; refined below)
        "ko": 0,  # Hangul
        "th": 0,  # Thai
        "hi": 0,  # Devanagari
        "el": 0,  # Greek
    }
    for ch in text:
        cp = ord(ch)
        if 0x0400 <= cp <= 0x04FF:
            counts["ru"] += 1
        elif 0x0600 <= cp <= 0x06FF:
            counts["ar"] += 1
        elif 0x0590 <= cp <= 0x05FF:
            counts["he"] += 1
        elif 0x3040 <= cp <= 0x30FF:  # Hiragana + Katakana → unambiguous ja
            counts["ja"] += 1
        elif 0x4E00 <= cp <= 0x9FFF:  # CJK Unified (shared zh/ja)
            counts["zh"] += 1
        elif 0xAC00 <= cp <= 0xD7AF:
            counts["ko"] += 1
        elif 0x0E00 <= cp <= 0x0E7F:
            counts["th"] += 1
        elif 0x0900 <= cp <= 0x097F:
            counts["hi"] += 1
        elif 0x0370 <= cp <= 0x03FF:
            counts["el"] += 1

    # If Hiragana/Katakana is present, the CJK block is Japanese, not Chinese.
    if counts["ja"] > 0:
        counts["zh"] = 0  # don't double-count as Chinese

    # Return the language whose script count exceeds the threshold.
    # Priority order resolves ties for mixed-script edge cases.
    for lang in ("ru", "ar", "he", "ja", "zh", "ko", "th", "hi", "el"):
        if counts[lang] >= threshold:
            return lang

    return "en"


# Classify query into up to 3 routing types (rules-based profiles).
def infer_query_types(query: str) -> list[str]:
    return infer_query_types_from_rules(query, limit=3)


# Extract years, journalistic intent, and query terms for scoring helpers.
def _parse_query_profile(query: str) -> dict:
    q = (query or "").lower()
    years = _YEAR_RE.findall(query)
    tokens = set(q.split())
    has_intent = bool(tokens & journalistic_intent_terms())
    return {"years": years, "has_intent": has_intent, "terms": _query_terms(query)}


_HUB_URL_SEGMENTS = frozenset({
    "category", "categories", "tag", "tags", "topic", "topics",
    "theme", "themes", "rubric", "rubrics", "section", "sections",
    "label", "labels", "archive", "archives", "feed", "rss",
    "search", "results", "page", "index", "catalog",
})
_HUB_TITLE_PHRASES = (
    "все новости", "последние новости", "все статьи",
    "all news", "all articles", "all posts", "news feed", "tag page",
    "category page", "topic page", "browse", "archive",
)


# Penalize hub/listing URLs and generic index pages in triage scoring.
def _hub_penalty(url: str, title: str, snippet: str) -> float:
    penalty = 0.0
    path_parts = set((urlparse(url).path or "").lower().strip("/").split("/"))
    if path_parts & _HUB_URL_SEGMENTS:
        penalty += 0.5
    path = (urlparse(url).path or "").strip("/")
    if not path or path in ("", "index", "index.html", "index.php"):
        penalty += 0.3
    if any(phrase in (title or "").lower() for phrase in _HUB_TITLE_PHRASES):
        penalty += 0.4
    snip = snippet or ""
    if snip.count(" · ") >= 3 or snip.count(" • ") >= 3 or snip.count(" | ") >= 4:
        penalty += 0.25
    return min(penalty, 1.0)


@dataclass
class TriageResult:
    skip: bool          # True → don't fetch, use snippet only
    fetch_policy: str   # "cheap" (httpx only) | "race" (httpx + curl_cffi parallel)
    score: float        # triage relevance score [0, 1]


@dataclass
class SearchCycleContext:
    raw_query: str
    analysis_query: str
    provider_query: str
    lang: str
    year_hint: str | None
    query_types: list[str]
    class_mix: list[QueryClassWeight]
    source_budget: dict[str, int]
    debug_trace: dict = field(default_factory=dict)


# Resolve pipeline mode from env or search_config (rules vs aslm_embedding).
def _pipeline_mode() -> str:
    from core.config.pipeline_modes import normalize_pipeline_mode

    env = os.environ.get("ASLM_WEB_SEARCH_PIPELINE")
    if env is not None:
        return normalize_pipeline_mode(env)
    return normalize_pipeline_mode(load_search_config().models.pipeline)


# Cached models section from search_config.
def _models_config():
    return load_search_config().models


# Neural stack runs only on high effort when pipeline is aslm_embedding.
def _neural_stack_enabled(effort: str | None = None) -> bool:
    if _pipeline_mode() == "rules":
        return False
    return _normalize_search_effort(effort) == "high"


# True when ASLM encoder should load for this effort.
def _neural_encoder_enabled(effort: str | None = None) -> bool:
    if not _neural_stack_enabled(effort):
        return False
    return _env_enabled(
        "ASLM_WEB_SEARCH_NEURAL_ENCODER",
        default=bool(_models_config().enable_encoder),
    )


# True when ASLM decoder should load for this effort.
def _neural_decoder_enabled(effort: str | None = None) -> bool:
    if not _neural_stack_enabled(effort):
        return False
    return _env_enabled(
        "ASLM_WEB_SEARCH_NEURAL_DECODER",
        default=bool(_models_config().enable_decoder),
    )


# True when encoder or decoder is active for this effort.
def _use_neural_pipeline(effort: str | None = None) -> bool:
    return _neural_encoder_enabled(effort) or _neural_decoder_enabled(effort)


# Which neural components (encoder, decoder) are enabled for this effort.
def _model_session_components(effort: str | None = None) -> tuple[bool, bool]:
    return _neural_encoder_enabled(effort), _neural_decoder_enabled(effort)


# Format top class scores for trace/debug output.
def _format_model_label_top(top: list[tuple[str, float]], limit: int = 5) -> list[list[Any]]:
    return [[name, round(float(score), 4)] for name, score in top[:limit]]


# Build encoder/decoder load status dict for neural session snapshots.
def _component_load_status(
    *,
    enabled: bool,
    requested: bool,
    loaded: bool,
    path: Path | None,
    error: str | None,
) -> dict[str, Any]:
    used = enabled and loaded
    if not enabled:
        status = "disabled"
    elif loaded:
        status = "loaded"
    elif requested:
        status = "load_failed"
    else:
        status = "not_requested"
    return {
        "enabled": enabled,
        "requested": requested,
        "loaded": loaded,
        "used": used,
        "status": status,
        "path": str(path) if path else None,
        "error": error,
    }


# Snapshot neural model session load state for tracing.
def _model_session_snapshot(
    model_session: SearchModelSession | None,
    effort: str | None,
) -> dict[str, Any]:
    from core.query.aslm_embedding_runtime import (
        default_query_classifier_path,
        default_source_relevance_path,
    )

    enc_enabled, dec_enabled = _model_session_components(effort)
    if model_session is None:
        return {
            "effort": effort,
            "device": _search_model_device() if (enc_enabled or dec_enabled) else None,
            "encoder": _component_load_status(
                enabled=enc_enabled,
                requested=enc_enabled,
                loaded=False,
                path=default_query_classifier_path() if enc_enabled else None,
                error="model_session_missing",
            ),
            "decoder": _component_load_status(
                enabled=dec_enabled,
                requested=dec_enabled,
                loaded=False,
                path=default_source_relevance_path() if dec_enabled else None,
                error="model_session_missing",
            ),
        }
    return {
        "effort": effort,
        "device": model_session.device,
        "encoder": _component_load_status(
            enabled=enc_enabled,
            requested=model_session.load_encoder,
            loaded=model_session.encoder is not None,
            path=getattr(model_session, "encoder_path", None) or (
                default_query_classifier_path() if model_session.load_encoder else None
            ),
            error=getattr(model_session, "encoder_load_error", None),
        ),
        "decoder": _component_load_status(
            enabled=dec_enabled,
            requested=model_session.load_decoder,
            loaded=model_session.decoder is not None,
            path=getattr(model_session, "decoder_path", None) or (
                default_source_relevance_path() if model_session.load_decoder else None
            ),
            error=getattr(model_session, "decoder_load_error", None),
        ),
    }


# Log neural encoder/decoder usage and classification debug to trace.
def _log_neural_usage(
    req_id: str,
    *,
    effort: str | None,
    model_session: SearchModelSession | None,
    class_debug: dict[str, Any] | None = None,
) -> None:
    snapshot = _model_session_snapshot(model_session, effort)
    _trace(req_id, "neural.session", **snapshot)

    enc = snapshot["encoder"]
    dec = snapshot["decoder"]
    if enc["status"] == "load_failed":
        logger.error(
            "req=%s ASLM encoder enabled but not loaded path=%s error=%s",
            req_id,
            enc.get("path"),
            enc.get("error"),
        )
    if dec["status"] == "load_failed":
        logger.error(
            "req=%s ASLM decoder enabled but not loaded path=%s error=%s",
            req_id,
            dec.get("path"),
            dec.get("error"),
        )

    if class_debug:
        mode = class_debug.get("mode", "unknown")
        encoder_used = enc["used"] and mode not in {"rules", "neural-unavailable"}
        _trace(
            req_id,
            "neural.encoder",
            used=encoder_used,
            mode=mode,
            model_score=class_debug.get("model_score"),
            model_top=class_debug.get("model_top"),
            best_rule_score=class_debug.get("best_rule_score"),
            classes=class_debug.get("classes"),
        )
        if encoder_used:
            logger.info(
                "req=%s encoder mode=%s score=%s top=%s classes=%s",
                req_id,
                mode,
                class_debug.get("model_score"),
                class_debug.get("model_top"),
                [item.get("name") for item in (class_debug.get("classes") or [])[:3]],
            )
        elif enc["enabled"]:
            reason = class_debug.get("reason") or class_debug.get("encoder_error") or mode
            level = logger.error if mode == "neural-unavailable" else logger.info
            level(
                "req=%s encoder not used mode=%s reason=%s",
                req_id,
                mode,
                reason,
            )


# Parse ASLM_WEB_SEARCH_* env flag (0/false/no/off → disabled).
def _env_enabled(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", "disabled"}


# True when neural models should stay loaded between searches.
def _keep_search_models_loaded() -> bool:
    return _env_enabled(
        "ASLM_WEB_SEARCH_KEEP_MODELS",
        default=bool(load_search_config().models.keep_loaded),
    )


# Device string for ASLM models (env or config, default cpu).
def _search_model_device() -> str:
    return (os.environ.get("ASLM_WEB_SEARCH_MODEL_DEVICE") or load_search_config().models.search_device or "cpu").strip().lower()


_MODEL_SESSION_LOCK = threading.RLock()
_SHARED_MODEL_SESSION: SearchModelSession | None = None


# Release the optional process-wide neural model session.
def clear_shared_search_model_session() -> None:
    global _SHARED_MODEL_SESSION
    with _MODEL_SESSION_LOCK:
        if _SHARED_MODEL_SESSION is not None:
            _SHARED_MODEL_SESSION.close()
        _SHARED_MODEL_SESSION = None


# True when a cached session matches requested encoder/decoder/device.
def _session_matches_components(
    session: SearchModelSession,
    *,
    load_encoder: bool,
    load_decoder: bool,
    device: str,
) -> bool:
    if session.device != device:
        return False
    return (
        (session.encoder is not None) == load_encoder
        and (session.decoder is not None) == load_decoder
    )


# Get or create the process-wide SearchModelSession (when keep_loaded).
def _get_shared_search_model_session(
    effort: str | None = None,
    *,
    load_encoder: bool,
    load_decoder: bool,
) -> SearchModelSession:
    global _SHARED_MODEL_SESSION
    with _MODEL_SESSION_LOCK:
        device = _search_model_device()
        if (
            _SHARED_MODEL_SESSION is None
            or not _SHARED_MODEL_SESSION.ready
            or not _session_matches_components(
                _SHARED_MODEL_SESSION,
                load_encoder=load_encoder,
                load_decoder=load_decoder,
                device=device,
            )
        ):
            if _SHARED_MODEL_SESSION is not None:
                _SHARED_MODEL_SESSION.close()
            session = SearchModelSession(
                load=True,
                device=device,
                load_encoder=load_encoder,
                load_decoder=load_decoder,
            )
            session.__enter__()
            _SHARED_MODEL_SESSION = session
        return _SHARED_MODEL_SESSION


# Context manager for per-search or shared neural model session.
@contextmanager
def _search_model_session_scope(effort: str | None = None):
    load_encoder, load_decoder = _model_session_components(effort)
    if not load_encoder and not load_decoder:
        if not _keep_search_models_loaded():
            clear_shared_search_model_session()
        with SearchModelSession(load=False) as model_session:
            yield model_session
        return
    if _keep_search_models_loaded():
        yield _get_shared_search_model_session(
            effort,
            load_encoder=load_encoder,
            load_decoder=load_decoder,
        )
        return
    with SearchModelSession(
        load=True,
        device=_search_model_device(),
        load_encoder=load_encoder,
        load_decoder=load_decoder,
    ) as model_session:
        yield model_session


# Convert class mix weights to legacy query type name list.
def _class_mix_to_legacy_types(class_mix: list[QueryClassWeight]) -> list[str]:
    return [item.name for item in class_mix] or ["general"]


# Build class mix from rules-only profile scoring.
def _build_legacy_class_mix(query: str) -> list[QueryClassWeight]:
    types = infer_query_types_from_rules(query, limit=3)
    if not types:
        return [QueryClassWeight("general", 1.0, "rules-empty")]
    return normalize_class_mix([
        QueryClassWeight(name, 1.0 / len(types), "rules-only")
        for name in types
    ])


# Build class mix via ASLM encoder with rules fallback and debug metadata.
def _build_neural_class_mix(query: str, model_session: SearchModelSession | None, effort: str | None = None) -> tuple[list[QueryClassWeight], dict]:
    if not _neural_encoder_enabled(effort):
        mix = _build_legacy_class_mix(query)
        return mix, {"mode": "rules", "encoder_enabled": False, "classes": [asdict(item) for item in mix]}
    if model_session is None:
        mix = _build_legacy_class_mix(query)
        return mix, {
            "mode": "neural-unavailable",
            "reason": "no_model_session",
            "classes": [asdict(item) for item in mix],
        }
    if model_session.encoder is None:
        mix = _build_legacy_class_mix(query)
        return mix, {
            "mode": "neural-unavailable",
            "reason": "encoder_not_loaded",
            "encoder_error": getattr(model_session, "encoder_load_error", None),
            "classes": [asdict(item) for item in mix],
        }
    prediction = model_session.classify_query(query)
    if prediction is None:
        mix = _build_legacy_class_mix(query)
        return mix, {"mode": "neural-unavailable", "reason": "classify_returned_none", "classes": [asdict(item) for item in mix]}
    rule_scores = score_query_against_profiles(query)
    has_rule_support = any(item.score >= 0.08 for item in rule_scores)
    best_rule_score = max((item.score for item in rule_scores), default=0.0)
    if prediction.score < 0.50 and best_rule_score >= 0.15:
        mix = _build_legacy_class_mix(query)
        return mix, {
            "mode": "rules-override-weak-encoder",
            "model_score": round(prediction.score, 4),
            "model_top": prediction.top(8),
            "best_rule_score": round(best_rule_score, 4),
            "classes": [asdict(item) for item in mix],
        }
    if prediction.score < 0.50 and not has_rule_support:
        mix = [QueryClassWeight("general", 1.0, "weak-model-no-rule-support")]
        return mix, {
            "mode": "aslm-embedding-weak-general-fallback",
            "model_score": round(prediction.score, 4),
            "model_top": prediction.top(8),
            "classes": [asdict(item) for item in mix],
        }
    hybrid = infer_query_types_hybrid(query, prediction.labels)
    mix = ensure_general_fallback(normalize_class_mix([
        QueryClassWeight(name, weight, reason)
        for name, weight, reason in hybrid
    ]))
    return mix, {
        "mode": "aslm_embedding",
        "model_score": round(prediction.score, 4),
        "model_top": prediction.top(8),
        "hybrid": hybrid,
        "classes": [asdict(item) for item in mix],
    }


# Cheap lexical/trust score used before preview fetching.
def _triage_soft_score(
    result: SearchResult,
    query: str,
    *,
    index: int,
    total: int,
) -> float:
    title = (result.title or "").strip()
    snippet = (result.snippet or "").strip()
    pos_score = 1.0 - (index / max(total - 1, 1))
    snip_score = min(1.0, len(snippet) / 300)
    lex = _lexical_score(query, title, snippet, result.url)
    tier_trust = _TIER_TRUST_SCORES.get(result.trust_tier or "unknown", 0.5)
    date_boost = 0.08 if _DATE_SIGNAL_RE.search(snippet) else 0.0
    hub_pen = _hub_penalty(result.url, title, snippet)
    routing = max(0.45, min(1.65, float(getattr(result, "routing_score", 1.0) or 1.0)))
    snippet_rel = max(0.0, min(1.0, float(getattr(result, "snippet_relevance_score", 0.0) or 0.0)))

    score = (
        0.25 * pos_score
        + 0.10 * snip_score
        + 0.40 * lex
        + 0.15 * tier_trust
        + 0.10 * snippet_rel
        + 0.08 * ((routing - 1.0) / 0.65)
        + date_boost
        - 0.20 * hub_pen
    )
    return max(0.0, min(1.0, score))


# Run cheap triage for one SERP result (skip/fetch_policy/score).
def _triage_one_result(
    result: SearchResult,
    query: str,
    *,
    index: int,
    total: int,
    trust_reg=None,
    rep_store=None,
) -> TriageResult:
    url = result.url
    title = (result.title or "").strip()
    snippet = (result.snippet or "").strip()
    title_lower = title.lower()

    _resolve_result_trust_tier(result, url, trust_reg=trust_reg, rep_store=rep_store)

    if len(snippet) < 30 or (len(snippet) < 60 and len(title) < 20):
        return TriageResult(skip=True, fetch_policy="cheap", score=0.0)

    if any(p in title_lower for p in _SKIP_TITLE_PATTERNS):
        return TriageResult(skip=True, fetch_policy="cheap", score=0.0)

    if trust_reg is not None:
        try:
            if trust_reg.is_blacklisted(url):
                return TriageResult(skip=True, fetch_policy="cheap", score=0.0)
        except Exception as _e:
            logger.debug("trust_reg.is_blacklisted failed for %s: %s", url, _e)

    if rep_store is not None:
        try:
            if rep_store.is_auto_blacklisted(domain_from_url(url)):
                return TriageResult(skip=True, fetch_policy="cheap", score=0.0)
        except Exception as _e:
            logger.debug("rep_store.is_auto_blacklisted failed for %s: %s", url, _e)

    score = _triage_soft_score(result, query, index=index, total=total)
    if score < 0.10:
        return TriageResult(skip=True, fetch_policy="cheap", score=score)
    if score >= 0.50:
        return TriageResult(skip=False, fetch_policy="race", score=score)
    return TriageResult(skip=False, fetch_policy="cheap", score=score)


# Cheap per-result triage; populates result.trust_tier when missing.
def _triage_results(results: list[SearchResult], query: str) -> list[TriageResult]:
    try:
        trust_reg = get_trust_registry()
    except Exception as _e:
        logger.debug("trust_registry unavailable: %s", _e)
        trust_reg = None

    try:
        rep_store = get_reputation_store()
    except Exception as _e:
        logger.debug("reputation_store unavailable: %s", _e)
        rep_store = None

    total = len(results)
    out: list[TriageResult] = []

    for idx, result in enumerate(results):
        out.append(
            _triage_one_result(
                result,
                query,
                index=idx,
                total=total,
                trust_reg=trust_reg,
                rep_store=rep_store,
            )
        )

    return out


# How many results from a single domain are allowed in the candidate pool
# before the cap kicks in. A lower number forces source diversity; 2 is safe
# for most cases and prevents arxiv (or any single aggregator) from flooding
# the top of academic/medical results when other sources are also relevant.
_DOMAIN_CAP_DEFAULT = 3
_DOMAIN_CAP_OVERRIDES: dict[str, int] = {
    "arxiv.org": 2,
}


# Enforce per-domain cap so one host cannot dominate the candidate pool.
def _apply_domain_cap(results: list[SearchResult]) -> list[SearchResult]:
    from urllib.parse import urlparse as _up
    counts: dict[str, int] = {}
    out: list[SearchResult] = []
    for result in results:
        host = _up(result.url or "").netloc.lower().removeprefix("www.")
        cap = _DOMAIN_CAP_OVERRIDES.get(host, _DOMAIN_CAP_DEFAULT)
        if counts.get(host, 0) >= cap:
            continue
        counts[host] = counts.get(host, 0) + 1
        out.append(result)
    return out


# Attach domain-registry routing_score and debug to each result.
def _apply_registry_routing(results: list[SearchResult], class_mix: list[QueryClassWeight]) -> None:
    for result in results:
        try:
            routing = compute_routing_score(result.url, class_mix)
            result.routing_score = routing.multiplier
            result.routing_debug = routing.debug
        except Exception as exc:
            logger.debug("routing_score failed url=%s: %s", result.url, exc)
            result.routing_score = 1.0
            result.routing_debug = {}


# Score SERP snippets with ASLM decoder when enabled.
def _apply_snippet_decoder(
    results: list[SearchResult],
    query: str,
    model_session: SearchModelSession | None,
    effort: str | None = None,
    *,
    req_id: str = "-",
) -> None:
    if not _neural_decoder_enabled(effort):
        _trace(req_id, "neural.decoder.snippet", used=False, reason="disabled_by_config")
        return
    if model_session is None:
        _trace(req_id, "neural.decoder.snippet", used=False, reason="no_model_session")
        logger.warning("req=%s snippet decoder skipped: model_session is None", req_id)
        return
    if model_session.decoder is None:
        error = getattr(model_session, "decoder_load_error", None) or "decoder_not_loaded"
        _trace(req_id, "neural.decoder.snippet", used=False, reason="decoder_not_loaded", error=error)
        logger.error("req=%s snippet decoder skipped: %s", req_id, error)
        return
    if not results:
        _trace(req_id, "neural.decoder.snippet", used=False, reason="no_results")
        return
    candidates = [
        {"title": r.title or "", "url": r.url or "", "snippet": r.snippet or ""}
        for r in results
    ]
    try:
        predictions = model_session.score_snippet_candidates(query, candidates)
    except Exception as exc:
        _trace(req_id, "neural.decoder.snippet", used=False, reason="inference_failed", error=str(exc))
        logger.error("req=%s snippet decoder inference failed: %s", req_id, exc, exc_info=True)
        return
    scores: list[float] = []
    sample: list[dict[str, Any]] = []
    for result, prediction in zip(results, predictions, strict=False):
        score = max(0.0, min(1.0, float(prediction.score or 0.0)))
        scores.append(score)
        result.snippet_relevance_score = score
        result.routing_debug = dict(result.routing_debug or {})
        result.routing_debug["snippet_decoder_top"] = prediction.top(5)
        if len(sample) < 5:
            sample.append({
                "url": (result.url or "")[:100],
                "score": round(score, 4),
                "top": _format_model_label_top(prediction.top(8)),
            })
    _trace(
        req_id,
        "neural.decoder.snippet",
        used=True,
        count=len(predictions),
        score_min=round(min(scores), 4) if scores else None,
        score_max=round(max(scores), 4) if scores else None,
        score_avg=round(sum(scores) / len(scores), 4) if scores else None,
        sample=sample,
    )
    logger.info(
        "req=%s snippet decoder scored=%d avg=%.3f max=%.3f",
        req_id,
        len(scores),
        sum(scores) / len(scores) if scores else 0.0,
        max(scores) if scores else 0.0,
    )


# Score fetched preview bodies with ASLM decoder when enabled.
def _apply_parsed_decoder(
    results: list[SearchResult],
    payloads: list[PreviewPayload],
    query: str,
    model_session: SearchModelSession | None,
    effort: str | None = None,
    *,
    req_id: str = "-",
) -> None:
    if not _neural_decoder_enabled(effort):
        _trace(req_id, "neural.decoder.parsed", used=False, reason="disabled_by_config")
        return
    if model_session is None:
        _trace(req_id, "neural.decoder.parsed", used=False, reason="no_model_session")
        logger.warning("req=%s parsed decoder skipped: model_session is None", req_id)
        return
    if model_session.decoder is None:
        error = getattr(model_session, "decoder_load_error", None) or "decoder_not_loaded"
        _trace(req_id, "neural.decoder.parsed", used=False, reason="decoder_not_loaded", error=error)
        logger.error("req=%s parsed decoder skipped: %s", req_id, error)
        return
    if not results:
        _trace(req_id, "neural.decoder.parsed", used=False, reason="no_results")
        return
    candidates = [
        {
            "title": r.title or "",
            "url": r.url or "",
            "snippet": r.snippet or "",
            "preview": p.text or "",
        }
        for r, p in zip(results, payloads, strict=False)
    ]
    try:
        predictions = model_session.score_parsed_candidates(query, candidates)
    except Exception as exc:
        _trace(req_id, "neural.decoder.parsed", used=False, reason="inference_failed", error=str(exc))
        logger.error("req=%s parsed decoder inference failed: %s", req_id, exc, exc_info=True)
        return
    scores: list[float] = []
    sample: list[dict[str, Any]] = []
    with_preview = 0
    for result, prediction, payload in zip(results, predictions, payloads, strict=False):
        score = max(0.0, min(1.0, float(prediction.score or 0.0)))
        scores.append(score)
        if (payload.text or "").strip():
            with_preview += 1
        result.parsed_relevance_score = score
        result.routing_debug = dict(result.routing_debug or {})
        result.routing_debug["parsed_decoder_top"] = prediction.top(5)
        if len(sample) < 5:
            sample.append({
                "url": (result.url or "")[:100],
                "score": round(score, 4),
                "preview_chars": len(payload.text or ""),
                "top": _format_model_label_top(prediction.top(8)),
            })
    _trace(
        req_id,
        "neural.decoder.parsed",
        used=True,
        count=len(predictions),
        with_preview=with_preview,
        score_min=round(min(scores), 4) if scores else None,
        score_max=round(max(scores), 4) if scores else None,
        score_avg=round(sum(scores) / len(scores), 4) if scores else None,
        sample=sample,
    )
    logger.info(
        "req=%s parsed decoder scored=%d with_preview=%d avg=%.3f max=%.3f",
        req_id,
        len(scores),
        with_preview,
        sum(scores) / len(scores) if scores else 0.0,
        max(scores) if scores else 0.0,
    )


# Normalize titles for conservative same-domain document-family deduplication.
def _document_family_title(title: str) -> str:
    normalized = (title or "").lower()
    has_version_marker = bool(
        re.search(r"\b(?:enterprise\s+server|server\s+version|version)\b", normalized)
    )
    normalized = re.sub(
        r"\b(?:enterprise\s+server|server\s+version|version)\b",
        " ",
        normalized,
    )
    if has_version_marker:
        normalized = re.sub(r"\bv?\d+(?:\.\d+){0,3}\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


# Dedup by normalized URL, domain+title, document family, and snippet signature.
def _dedup_results(results: list[SearchResult]) -> list[SearchResult]:
    seen_urls: set[str] = set()
    seen_keys: set[str] = set()
    out: list[SearchResult] = []
    for r in results:
        nu = normalize_url(r.url)
        if nu in seen_urls:
            continue
        seen_urls.add(nu)
        domain = urlparse(r.url).netloc.lower()
        title_key = f"{domain}||{r.title.strip().lower()[:60]}"
        family_title = _document_family_title(r.title)
        family_key = f"{domain}||family||{family_title[:100]}" if len(family_title) >= 16 else ""
        snip_key = " ".join((r.snippet or "").lower().split()[:20])
        if (
            title_key in seen_keys
            or (family_key and family_key in seen_keys)
            or (snip_key and snip_key in seen_keys)
        ):
            continue
        seen_keys.add(title_key)
        if family_key:
            seen_keys.add(family_key)
        if snip_key:
            seen_keys.add(snip_key)
        out.append(r)
    return out


_TIER_TRUST_SCORES = {
    "A": 1.0,
    "B": 0.75,
    "C": 0.45,
    "friendly": 1.0,
    "moderate": 0.75,
    "hardened": 0.35,
    "fortress": 0.05,
    "?": 0.50,
    "unknown": 0.50,
}

_TRUST_BLEND_WEIGHTS: dict[str, tuple[float, float]] = {
    "academic": (0.80, 0.20),
    "medical": (0.80, 0.20),
    "technical": (0.70, 0.30),
    "shopping": (0.55, 0.45),
    "forum": (0.55, 0.45),
    "journalistic": (0.60, 0.40),
    "finance": (0.60, 0.40),
    "general": (0.65, 0.35),
}


# Static/dynamic trust blend weights for lexical scoring by query type.
def _trust_blend_weights(query_type: str) -> tuple[float, float]:
    return _TRUST_BLEND_WEIGHTS.get(query_type, _TRUST_BLEND_WEIGHTS["general"])


# Small score boost for academic: engine results on academic/medical queries.
def _academic_engine_bonus(result: SearchResult, query_type: str) -> float:
    if query_type not in {"academic", "medical"}:
        return 0.0
    engine = (result.engine or "").lower()
    if not engine.startswith("academic:"):
        return 0.0

    bonus = 0.10
    url_l = (result.url or "").lower()
    snippet_l = (result.snippet or "").lower()
    if "doi.org/" in url_l:
        bonus += 0.02
    if any(token in snippet_l for token in ("abstract", "journal", "trial", "cohort", "doi", "pmid")):
        bonus += 0.02
    return min(bonus, 0.14)


# Boost when preview/body years match query year anchors; penalize mismatch.
def _year_match_score(text: str, years: list[str]) -> float:
    if not years or not text:
        return 0.0
    text_l = text.lower()
    found_years = set(_YEAR_RE.findall(text_l))
    if not found_years:
        return 0.0
    hits = set(years) & found_years
    return 1.0 if hits else -0.3


_PARSED_LEX_BODY_CHARS = 4_000
# Body must beat SERP-only lexical by at least this much to earn a separate boost.
_PARSED_LEX_MARGIN = 0.04


# Lexical overlap using SERP fields plus fetched preview body text.
def _parsed_lexical_score(
    query: str,
    result: SearchResult,
    payload: PreviewPayload,
) -> float:
    body = (payload.text or "").strip()
    if not body:
        return 0.0
    combined_snippet = " ".join(
        filter(None, [result.snippet or "", body[:_PARSED_LEX_BODY_CHARS]]),
    )
    return _lexical_score(
        query,
        result.title or "",
        combined_snippet,
        result.url or "",
    )


# Combined rerank score: lexical, neural, trust, routing, and hub penalty.
def _result_score(
    result: SearchResult,
    payload: PreviewPayload,
    *,
    index: int,
    total: int,
    query: str,
    profile: dict,
    query_type: str = "general",
    rep_store=None,
) -> float:
    original_rank = 1.0 if total <= 1 else 1.0 - (index / max(total - 1, 1))
    lex = _lexical_score(query, result.title or "", result.snippet or "", result.url)
    parsed_lex = _parsed_lexical_score(query, result, payload)
    hub_pen = _hub_penalty(result.url, result.title or "", result.snippet or "")

    # Trust component: blend static tier with dynamic reputation score.
    # The blend is query-type aware so ranking can trust curated registries
    # more for safety-critical domains and react faster to dynamic quality in
    # volatile domains (shopping/forum/news).
    tier = result.trust_tier or "unknown"
    static_trust = _TIER_TRUST_SCORES.get(tier, None)  # None = not in static registry
    if rep_store is not None:
        domain = domain_from_url(result.url)
        rep_score = rep_store.get_reputation_score(domain, query_type)
    else:
        rep_score = 0.50

    if static_trust is not None:
        static_weight, dynamic_weight = _trust_blend_weights(query_type)
        trust = static_weight * static_trust + dynamic_weight * rep_score
    else:
        trust = rep_score

    full_text = " ".join(filter(None, [result.title, result.snippet, payload.text or ""]))
    year_score = _year_match_score(full_text, profile["years"]) if profile["years"] else 0.0
    routing = max(0.45, min(1.65, float(getattr(result, "routing_score", 1.0) or 1.0)))
    snippet_rel = max(0.0, min(1.0, float(getattr(result, "snippet_relevance_score", 0.0) or 0.0)))
    parsed_rel = max(0.0, min(1.0, float(getattr(result, "parsed_relevance_score", 0.0) or 0.0)))
    decoder_rel = parsed_rel if payload.text else snippet_rel
    semantic_component = max(
        0.0,
        min(
            1.0,
            0.55 * max(0.0, min(payload.semantic_score, 1.0))
            + 0.45 * decoder_rel,
        ),
    )

    quality = max(0.0, min(float(payload.quality_score or 0.0), 1.0))
    if parsed_lex > lex + _PARSED_LEX_MARGIN:
        score = (
            0.18 * original_rank
            + 0.16 * lex
            + 0.18 * parsed_lex
            + 0.30 * semantic_component
            + 0.10 * trust
            + 0.08 * quality
        )
    else:
        score = (
            0.20 * original_rank
            + 0.20 * lex
            + 0.35 * semantic_component
            + 0.12 * trust
            + 0.08 * quality
        )
    if profile["years"]:
        score += 0.20 * year_score
    score -= 0.30 * hub_pen
    score += _academic_engine_bonus(result, query_type)
    score *= max(0.85, min(1.20, routing))
    return max(0.0, score)


# Content quality signal for reputation recording (no rank/trust position).
def _content_quality_signal(payload: PreviewPayload, result: SearchResult, query: str) -> float:
    lex = _lexical_score(query, result.title or "", result.snippet or "", result.url)
    parsed_lex = _parsed_lexical_score(query, result, payload)
    lex_component = (
        max(lex, parsed_lex) if parsed_lex > lex + _PARSED_LEX_MARGIN else lex
    )
    quality = max(0.0, min(float(payload.quality_score or 0.0), 1.0))
    semantic = max(0.0, min(float(payload.semantic_score or 0.0), 1.0))
    snippet_rel = max(0.0, min(1.0, float(getattr(result, "snippet_relevance_score", 0.0) or 0.0)))
    parsed_rel = max(0.0, min(1.0, float(getattr(result, "parsed_relevance_score", 0.0) or 0.0)))
    relevance = parsed_rel if (payload.text or "").strip() else snippet_rel
    if not relevance:
        relevance = snippet_rel

    if semantic > 0.0:
        return min(
            1.0,
            0.35 * semantic + 0.25 * quality + 0.25 * relevance + 0.15 * lex_component,
        )
    return min(1.0, 0.30 * quality + 0.40 * relevance + 0.30 * lex_component)


_MAX_RERANK_SHIFT = 3


# Reorder by measured score while keeping every result near its provider rank.
def _bounded_rerank(
    scored: list[tuple[float, int, SearchResult, PreviewPayload]],
    *,
    max_shift: int = _MAX_RERANK_SHIFT,
) -> list[tuple[float, int, SearchResult, PreviewPayload]]:
    if len(scored) <= 1 or max_shift <= 0:
        return sorted(scored, key=lambda item: item[1])

    remaining = list(scored)
    ordered: list[tuple[float, int, SearchResult, PreviewPayload]] = []
    for position in range(len(scored)):
        eligible = [item for item in remaining if item[1] - max_shift <= position]
        overdue = [item for item in eligible if item[1] + max_shift <= position]
        if overdue:
            chosen = min(overdue, key=lambda item: (item[1] + max_shift, -item[0], item[1]))
        else:
            chosen = min(eligible, key=lambda item: (-item[0], item[1]))
        ordered.append(chosen)
        remaining.remove(chosen)
    return ordered


# Fill trust_tier from static registry, then dynamic auto-promote.
def _resolve_result_trust_tier(
    result: SearchResult,
    url: str,
    *,
    trust_reg,
    rep_store,
) -> None:
    if (result.trust_tier or "?") != "?":
        return
    if trust_reg is not None:
        tier = trust_reg.get_tier(url)
        if tier:
            result.trust_tier = tier
            return
    if rep_store is not None:
        try:
            promoted = rep_store.get_promoted_tier(domain_from_url(url))
            if promoted in {"B", "C"}:
                result.trust_tier = promoted
        except Exception as _e:
            logger.debug("rep_store.get_promoted_tier failed for %s: %s", url, _e)


from core.fetch.constants import DEFAULT_UA as _UA
_PREFETCH_MAX_URLS: int = 5   # cap on background prefetch targets per search
# Limit concurrent background prefetch tasks to avoid socket exhaustion under burst load.
_PREFETCH_SEMAPHORE: Optional[asyncio.Semaphore] = None


# Semaphore limiting concurrent background prefetch tasks.
def _get_prefetch_semaphore() -> asyncio.Semaphore:
    global _PREFETCH_SEMAPHORE
    if _PREFETCH_SEMAPHORE is None:
        _PREFETCH_SEMAPHORE = asyncio.Semaphore(3)
    return _PREFETCH_SEMAPHORE


# Fire-and-forget: prefetch uncached URLs into SourceCache (HTML only, no antibot).
async def _prefetch_urls_background(urls: list[str], req_id: str = "-") -> None:
    import aiohttp as _aiohttp

    to_fetch: list[str] = []
    for url in urls:
        try:
            validate_public_fetch_url(url)
        except UnsafeFetchUrl as exc:
            _trace(req_id, "prefetch.blocked", url=url, reason=str(exc))
            continue
        if not _cache.is_fresh(url):
            to_fetch.append(url)
    if not to_fetch:
        return

    sem = _get_prefetch_semaphore()
    if not sem._value:
        # All prefetch slots are occupied — skip rather than queue more fetches.
        _trace(req_id, "prefetch.skipped", reason="semaphore_full")
        return

    _trace(req_id, "prefetch.start", urls=len(to_fetch))
    async with sem:
        try:
            connector = await _get_http_connector(concurrency=len(to_fetch) + 2)
            timeout = _aiohttp.ClientTimeout(total=float(load_search_config().search.prefetch_fetch_timeout))
            async with _aiohttp.ClientSession(
                connector=connector, connector_owner=False,
                timeout=timeout, headers={"User-Agent": _UA},
            ) as session:
                for url in to_fetch:
                    try:
                        raw_html = await _aiohttp_get_text_checked(
                            session,
                            url,
                            content_tokens=("html", "text"),
                        )
                        if raw_html and not is_antibot(raw_html):
                            clean_text = normalize_page(url, raw_html, "")
                            if clean_text:
                                _cache.cache_page(url, "", clean_text=clean_text)
                                _trace(req_id, "prefetch.cached", url=url)
                    except UnsafeFetchUrl as _e:
                        _trace(req_id, "prefetch.blocked", url=url, reason=str(_e))
                    except Exception as _e:
                        logger.debug("prefetch fetch failed for %s: %s", url, _e)
        except Exception as _e:
            logger.debug("prefetch batch error: %s", _e)




# Download PDF, extract text, densify with GliNER (tight preview caps).
async def _fetch_pdf_preview(
    url: str,
    query: str,
    loop,
    req_id: str = "-",
) -> PreviewPayload:
    _UA_PDF = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    search_cfg = load_search_config().search

    def _fetch_bytes() -> bytes:
        # httpx streaming with size guard
        try:
            import httpx
            current_url = validate_public_fetch_url(url)
            with httpx.Client(
                headers={"User-Agent": _UA_PDF, "Accept": "application/pdf,*/*;q=0.8"},
                timeout=float(search_cfg.pdf_preview_fetch_timeout),
                follow_redirects=False,
                verify=True,
            ) as client:
                for _ in range(max_safe_redirects() + 1):
                    with client.stream("GET", current_url) as r:
                        if _is_redirect_status(r.status_code):
                            current_url = validate_redirect_target(current_url, r.headers.get("location", ""))
                            continue
                        try:
                            content_length = int(r.headers.get("content-length", "0") or "0")
                        except ValueError:
                            content_length = 0
                        if content_length > _PDF_PREVIEW_MAX_BYTES:
                            return b""
                        chunks: list[bytes] = []
                        total = 0
                        for chunk in r.iter_bytes():
                            total += len(chunk)
                            if total > _PDF_PREVIEW_MAX_BYTES:
                                return b""
                            chunks.append(chunk)
                        data = b"".join(chunks)
                        if 200 <= r.status_code < 400 and looks_like_pdf_bytes(data):
                            return data
                        return b""
        except UnsafeFetchUrl as _e:
            logger.warning("blocked unsafe pdf preview url=%r reason=%s", url, _e)
            return b""
        except Exception as _e:
            logger.debug("pdf httpx fetch failed for %s: %s", url, _e)
        # curl_cffi fallback
        try:
            from curl_cffi import requests as cffi_req
            current_url = validate_public_fetch_url(url)
            for _ in range(max_safe_redirects() + 1):
                r = cffi_req.get(
                    current_url, impersonate="chrome124", timeout=float(search_cfg.pdf_preview_fetch_timeout),
                    headers={"User-Agent": _UA_PDF, "Accept": "application/pdf,*/*;q=0.8"},
                    allow_redirects=False,
                )
                if _is_redirect_status(int(r.status_code)):
                    current_url = validate_redirect_target(current_url, r.headers.get("location", ""))
                    continue
                break
            else:
                return b""
            data = bytes(r.content or b"")
            if 200 <= r.status_code < 400 and len(data) <= _PDF_PREVIEW_MAX_BYTES and looks_like_pdf_bytes(data):
                return data
        except UnsafeFetchUrl as _e:
            logger.warning("blocked unsafe pdf preview curl url=%r reason=%s", url, _e)
            return b""
        except Exception as _e:
            logger.debug("pdf curl_cffi fetch failed for %s: %s", url, _e)
        return b""

    t0 = time.perf_counter()
    raw_bytes = await loop.run_in_executor(_io_pool,_fetch_bytes)
    if not raw_bytes:
        _trace(req_id, "pdf_preview.empty", url=url, elapsed=round(time.perf_counter() - t0, 3))
        return PreviewPayload()

    def _extract_and_densify() -> str:
        markdown = pdf_bytes_to_markdown(url=url, data=raw_bytes, max_chars=_PDF_PREVIEW_MAX_CHARS)
        if not markdown:
            return ""
        return _densify_text_gliner(markdown, output_chars=_PDF_PREVIEW_OUTPUT_CHARS)

    try:
        text = await asyncio.wait_for(
            loop.run_in_executor(_io_pool,_extract_and_densify),
            timeout=float(search_cfg.pdf_preview_extract_timeout),
        )
    except Exception as _e:
        logger.debug("pdf extract failed for %s: %s", url, _e)
        text = ""

    elapsed = round(time.perf_counter() - t0, 3)
    if not text:
        _trace(req_id, "pdf_preview.extract_failed", url=url, elapsed=elapsed)
        return PreviewPayload()

    _trace(req_id, "pdf_preview.done", url=url, elapsed=elapsed, chars=len(text))
    return PreviewPayload(text=text, quality_score=0.75, strategy_used="pdf_gliner")


# Fetch one page preview (policy cheap = aiohttp only, race = aiohttp + curl_cffi).
async def _fetch_preview_one(
    session,
    result: SearchResult,
    query: str,
    settings: dict,
    sem: asyncio.Semaphore,
    loop,
    policy: str = "cheap",
    fetch_timeout: float | None = None,
    req_id: str = "-",
) -> PreviewPayload:
    async with sem:
        if fetch_timeout is None:
            fetch_timeout = float(load_search_config().search.preview_fetch_timeout)
        url = result.url
        t0 = time.perf_counter()
        try:
            validate_public_fetch_url(url)
        except UnsafeFetchUrl as exc:
            logger.warning("blocked unsafe preview candidate url=%r reason=%s", url, exc)
            _trace(req_id, "preview_fetch.blocked", url=url, reason=str(exc))
            return PreviewPayload()

        # Domain registry: honour method=skip and json_api_hint early.
        try:
            _dom_strategy = get_registry().resolve_access_strategy(url)
            if _dom_strategy.method == "skip":
                _trace(req_id, "preview_fetch.skip_domain", url=url, reason="method=skip")
                return PreviewPayload()
        except Exception as _dom_exc:
            logger.debug("domain registry access strategy failed for %s: %s", url, _dom_exc)

        # PDF fast-path: skip HTML fetch entirely, download bytes and densify
        if looks_like_pdf_url(url):
            return await _fetch_pdf_preview(url, query, loop, req_id=req_id)

        if is_stackexchange_question_url(url):
            text = await fetch_stackexchange_question(url, timeout=fetch_timeout)
            if text and not text.startswith("Error:"):
                _cache.cache_page(url, result.title or "", clean_text=text)
                _trace(
                    req_id,
                    "preview_fetch.done",
                    url=url,
                    policy="stackexchange_api",
                    elapsed=round(time.perf_counter() - t0, 3),
                    chars=len(text),
                    quality=0.85,
                    semantic=0.0,
                    strategy="stackexchange_api",
                )
                return PreviewPayload(text=text, quality_score=0.85, strategy_used="stackexchange_api")
            _trace(req_id, "preview_fetch.empty", url=url, policy="stackexchange_api", elapsed=round(time.perf_counter() - t0, 3))
            return PreviewPayload()

        if is_github_url(url):
            text = await fetch_github_page(url, timeout=fetch_timeout)
            if text and not text.lstrip().lower().startswith("error:"):
                _cache.cache_page(url, result.title or "", clean_text=text)
                _trace(
                    req_id,
                    "preview_fetch.done",
                    url=url,
                    policy="github_api",
                    elapsed=round(time.perf_counter() - t0, 3),
                    chars=len(text),
                    quality=0.90,
                    semantic=0.0,
                    strategy="github_api",
                )
                return PreviewPayload(text=text, quality_score=0.90, strategy_used="github_api")
            _trace(req_id, "preview_fetch.empty", url=url, policy="github_api", elapsed=round(time.perf_counter() - t0, 3))

        from custom_domains.router import get_custom_route
        _route = get_custom_route(url)
        if _route and not _route.is_heavy:
            text = await _route.fetch_preview(url, fetch_timeout)
            if text:
                _cache.cache_page(url, result.title or "", clean_text=text)
                _trace(
                    req_id,
                    "preview_fetch.done",
                    url=url,
                    policy=f"custom:{_route.name}",
                    elapsed=round(time.perf_counter() - t0, 3),
                    chars=len(text),
                    quality=_route.quality_score,
                    semantic=0.0,
                    strategy=f"custom:{_route.name}",
                )
                return PreviewPayload(
                    text=text,
                    quality_score=_route.quality_score,
                    strategy_used=f"custom:{_route.name}",
                )
            _trace(req_id, "preview_fetch.empty", url=url, policy=f"custom:{_route.name}", elapsed=round(time.perf_counter() - t0, 3))
            return PreviewPayload()

        async def _aiohttp() -> str | None:
            try:
                text = await _aiohttp_get_text_checked(session, url)
                return text if text and not is_antibot(text) else None
            except UnsafeFetchUrl as exc:
                logger.warning("blocked unsafe preview url=%r reason=%s", url, exc)
                return None
            except Exception:
                return None

        async def _curl() -> str | None:
            def _sync() -> str | None:
                try:
                    text = _curl_get_text_checked(
                        url,
                        timeout=int(load_search_config().search.preview_curl_timeout),
                        headers={"User-Agent": _UA},
                    )
                    return text if text and not is_antibot(text) else None
                except UnsafeFetchUrl as exc:
                    logger.warning("blocked unsafe preview curl url=%r reason=%s", url, exc)
                    return None
                except Exception:
                    return None
            return await loop.run_in_executor(_io_pool,_sync)

        # Fast path: if clean_text is already cached, skip fetch + parse entirely.
        # If hosted providers pre-populated raw_html (for example Tavily raw_content),
        # reuse it as the extraction input instead of doing a second network fetch.
        cached_page = _cache.get_cached(url)
        cached_raw_html = ""
        if cached_page and _cache.is_fresh(url):
            if cached_page.clean_text:
                return PreviewPayload(text=cached_page.clean_text)
            cached_raw_html = cached_page.raw_html or ""

        raw_html: str | None = cached_raw_html or None
        if not raw_html:
            if policy == "cheap":
                raw_html = await _aiohttp()
            else:
                # Race: both launched immediately; first non-None result wins
                t_aio = asyncio.create_task(_aiohttp())
                t_curl = asyncio.create_task(_curl())
                pending: set = {t_aio, t_curl}
                while pending and raw_html is None:
                    done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        try:
                            candidate = task.result()
                            if candidate:
                                raw_html = candidate
                                for p in pending:
                                    p.cancel()
                                pending = set()
                                break
                        except Exception as _e:
                            logger.debug("preview race task failed for %s: %s", url, _e)

        if not raw_html:
            _trace(req_id, "preview_fetch.empty", url=url, policy=policy, elapsed=round(time.perf_counter() - t0, 3))
            return PreviewPayload()

        preview_settings = dict(settings or {})
        preview_settings["serp_snippet"] = (result.snippet or "").strip()
        preview_settings["serp_title"] = (result.title or "").strip()
        try:
            payload = await asyncio.wait_for(
                loop.run_in_executor(
                    _io_pool,
                    lambda u=url, html=raw_html, q=query, ps=preview_settings: build_preview_payload(
                        u, html, query=q, settings=ps,
                    ),
                ),
                timeout=fetch_timeout,
            )
        except Exception as exc:
            logger.debug("preview payload build failed for %s: %s", url, exc)
            _trace(req_id, "preview_fetch.payload_error", url=url, policy=policy, elapsed=round(time.perf_counter() - t0, 3))
            return PreviewPayload()

        # Cache the processed text so future hits skip fetch + parse.
        if payload.text:
            _cache.cache_page(
                url,
                result.title or "",
                clean_text=payload.text,
                raw_html=raw_html or cached_raw_html,
            )
        _trace(
            req_id,
            "preview_fetch.done",
            url=url,
            policy=policy,
            elapsed=round(time.perf_counter() - t0, 3),
            chars=len(payload.text or ""),
            quality=round(float(payload.quality_score or 0.0), 3),
            semantic=round(float(payload.semantic_score or 0.0), 3),
            strategy=payload.strategy_used,
        )
        return payload


# Fetch previews concurrently; optional early_return_threshold cancels stragglers.
async def _fetch_previews(
    results: list[SearchResult],
    query: str,
    concurrency: int,
    fetch_timeout: float,
    total_timeout: float,
    preview_settings: dict,
    loop,
    policies: list[str] | None = None,
    early_return_threshold: int = 0,
    req_id: str = "-",
    deadline: float | None = None,
) -> list[PreviewPayload]:
    import aiohttp
    import math as _math

    if not results:
        return []

    if policies is None:
        policies = ["cheap"] * len(results)

    sem = asyncio.Semaphore(concurrency)
    timeout = aiohttp.ClientTimeout(total=fetch_timeout)
    connector = aiohttp.TCPConnector(
        limit=max(1, concurrency) * 4,
        limit_per_host=2,
        ttl_dns_cache=120,
    )
    t0 = time.perf_counter()
    _trace(
        req_id,
        "preview_batch.start",
        targets=len(results),
        concurrency=concurrency,
        fetch_timeout=fetch_timeout,
        total_timeout=total_timeout,
        early_return_threshold=early_return_threshold,
    )

    try:
        warm_t0 = time.perf_counter()
        await asyncio.wait_for(
            loop.run_in_executor(_io_pool,lambda: warm_preview_models(preview_settings)),
            timeout=float(load_search_config().search.preview_model_warm_timeout),
        )
        _trace(req_id, "preview_batch.warm_done", elapsed=round(time.perf_counter() - warm_t0, 3))
    except Exception:
        _trace(req_id, "preview_batch.warm_failed", elapsed=round(time.perf_counter() - warm_t0, 3))
        pass

    try:
        async with aiohttp.ClientSession(
            timeout=timeout, connector=connector, connector_owner=True,
            headers={"User-Agent": _UA}
        ) as session:
            tasks = [
                asyncio.create_task(
                    _fetch_preview_one(session, r, query, preview_settings, sem, loop, policy=p,
                                       fetch_timeout=fetch_timeout, req_id=req_id)
                )
                for r, p in zip(results, policies)
            ]
            effective_timeout = max(
                total_timeout,
                (fetch_timeout * _math.ceil(len(results) / max(concurrency, 1))) + 2.0,
            )
            if deadline is not None:
                # Leave 1s for formatting/ranking after previews finish
                remaining = max(1.0, deadline - loop.time() - 1.0)
                effective_timeout = min(effective_timeout, remaining)
            _trace(req_id, "preview_batch.effective_timeout", effective_timeout=effective_timeout)

            # Map task → original index so we can reconstruct ordering
            task_to_idx = {t: i for i, t in enumerate(tasks)}
            payloads: list[PreviewPayload] = [PreviewPayload()] * len(results)
            pending: set = set(tasks)
            good_count = 0
            deadline = loop.time() + effective_timeout

            while pending:
                remaining = max(0.01, deadline - loop.time())
                done_batch, pending = await asyncio.wait(
                    pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
                )
                if not done_batch:
                    # Deadline reached
                    break
                for task in done_batch:
                    idx = task_to_idx[task]
                    try:
                        payload = task.result()
                    except Exception as _e:
                        logger.debug("preview task failed for idx=%d: %s", idx, _e)
                        payload = PreviewPayload()
                    payloads[idx] = payload
                    if payload.text:
                        good_count += 1

                if early_return_threshold and good_count >= early_return_threshold:
                    for t in pending:
                        t.cancel()
                    logger.debug(
                        "early_return: %d good preview(s) collected, cancelled %d remaining",
                        good_count, len(pending),
                    )
                    _trace(
                        req_id,
                        "preview_batch.early_return",
                        good_count=good_count,
                        cancelled=len(pending),
                    )
                    break

            # Cancel any tasks still pending (deadline exceeded without early-return)
            for t in pending:
                t.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    except Exception as exc:
        logger.debug("preview batch failed: %s", exc, exc_info=True)
        _trace(req_id, "preview_batch.error", elapsed=round(time.perf_counter() - t0, 3))
        return [PreviewPayload() for _ in results]
    failures = sum(1 for p in payloads if not p.text)
    _trace(
        req_id,
        "preview_batch.done",
        elapsed=round(time.perf_counter() - t0, 3),
        nonempty=sum(1 for p in payloads if p.text),
        total=len(payloads),
        fetch_failures=failures,
        fallback_path="aiohttp_to_curl_race",
    )
    return payloads

# ---------------------------------------------------------------------------
# Per-query-type caps: result count, preview depth, unparsed bonus thresholds.
@dataclass
class _OutputProfile:
    max_results: int           # final result count shown to the model
    preview_fetch_limit: int   # max pages to actually scrape
    unparsed_bonus: int        # unparsed results appended if score ≥ threshold
    min_score_unparsed: float  # final-score floor for unparsed bonus results


_DEPTH_PREVIEW_TYPES: frozenset[str] = frozenset({
    "technical", "academic", "medical", "troubleshooting",
})


# Max preview chars shown in formatted output by query type and effort.
def _preview_display_limit(query_type: str | None, *, low_effort: bool) -> int:
    if low_effort:
        return 320
    if (query_type or "general").lower() in _DEPTH_PREVIEW_TYPES:
        return 2400
    return 1600


# Merge query-type chunk policy into preview extraction settings.
def _configure_preview_settings(
    preview_settings: dict,
    *,
    query_type: str,
) -> dict:
    from core.extract.profile_chunk_selector import resolve_chunk_policy

    settings = dict(preview_settings)
    settings["query_type"] = query_type
    policy = resolve_chunk_policy(query_type, char_budget=settings.get("output_chars"))
    settings["output_chars"] = policy.char_budget
    return settings


_OUTPUT_PROFILES: dict[str, _OutputProfile] = {
    # depth-first: fewer sources, deep parse — quality beats volume
    "technical":       _OutputProfile(6,  5, 2, 0.30),
    "academic":        _OutputProfile(6,  5, 1, 0.35),
    "troubleshooting": _OutputProfile(7,  5, 2, 0.28),
    "medical":         _OutputProfile(7,  5, 2, 0.28),
    # breadth-first: more sources, shallow parse — volume beats depth
    "journalistic":    _OutputProfile(12, 3, 0, 0.00),
    "forum":           _OutputProfile(10, 3, 0, 0.00),
    "shopping":        _OutputProfile(10, 3, 0, 0.00),
    # middle ground
    "finance":         _OutputProfile(8,  3, 2, 0.30),
    "general":         _OutputProfile(10, 4, 2, 0.30),
}
_DEFAULT_OUTPUT_PROFILE = _OUTPUT_PROFILES["general"]
_ADAPTIVE_BREADTH_QUERY_TYPES: frozenset[str] = frozenset({"technical", "troubleshooting"})


# Return depth-first or breadth-first output profile for the primary query type.
def _get_output_profile(query_types: list[str]) -> _OutputProfile:
    return _OUTPUT_PROFILES.get(query_types[0] if query_types else "general",
                                _DEFAULT_OUTPUT_PROFILE)


# Normalize effort aliases (normal/default → medium).
def _normalize_search_effort(effort: str | None) -> str:
    value = str(effort or "").strip().lower()
    value = _SEARCH_EFFORT_ALIASES.get(value, value)
    return value if value in _SEARCH_EFFORT_VALUES else "medium"


# True when search effort is low (snippet-only, no previews).
def _is_low_effort(opts: WebSearchOptions) -> bool:
    return _normalize_search_effort(opts.effort) == "low"


# Scale max_results and preview limits for high effort.
def _scale_output_profile(profile: _OutputProfile, multiplier: int) -> _OutputProfile:
    scaled = replace(profile)
    scaled.max_results = max(1, int(profile.max_results) * multiplier)
    scaled.preview_fetch_limit = max(0, int(profile.preview_fetch_limit) * multiplier)
    scaled.unparsed_bonus = max(0, int(profile.unparsed_bonus) * multiplier)
    return scaled


# Apply low/high effort overrides to an output profile.
def _apply_effort_to_output_profile(profile: _OutputProfile, opts: WebSearchOptions) -> _OutputProfile:
    effort = _normalize_search_effort(opts.effort)
    if effort == "low":
        low = replace(profile)
        low.max_results = min(low.max_results, opts.max_results)
        low.preview_fetch_limit = 0
        low.unparsed_bonus = 0
        return low
    if effort == "high":
        return _scale_output_profile(profile, max(1, int(opts.effort_multiplier)))
    return profile


# Re-apply low-effort caps after adaptive profile widening.
def _enforce_effort_after_adaptation(profile: _OutputProfile, opts: WebSearchOptions) -> _OutputProfile:
    if _normalize_search_effort(opts.effort) == "low":
        return _apply_effort_to_output_profile(profile, opts)
    return profile


# Final model-visible result cap (profile vs opts.max_results).
def _effective_output_limit(profile: _OutputProfile, opts: WebSearchOptions) -> int:
    return max(1, min(int(profile.max_results), int(opts.max_results)))


# Widen technical/troubleshooting output when preview evidence is thin.
def _adapt_output_profile(
    results: list[SearchResult],
    triage: list[TriageResult],
    base_profile: _OutputProfile,
    *,
    query_types: list[str],
    payloads: list[PreviewPayload] | None = None,
) -> tuple[_OutputProfile, dict[str, object]]:
    primary = query_types[0] if query_types else "general"
    meta: dict[str, object] = {
        "applied": False,
        "query_type": primary,
        "reasons": [],
    }
    if primary not in _ADAPTIVE_BREADTH_QUERY_TYPES or not results or not triage:
        return base_profile, meta

    profile = replace(base_profile)
    top_window = min(len(results), max(profile.max_results + 2, 8))
    top_results = results[:top_window]
    top_triage = triage[:top_window]
    top_scores = [float(item.score or 0.0) for item in top_triage if not item.skip]
    domains = [domain_from_url(item.url) for item in top_results if domain_from_url(item.url)]
    domain_diversity = len(set(domains))
    low_diversity = domain_diversity < min(4, len(top_results))
    clustered_scores = (
        len(top_scores) >= 3
        and (top_scores[0] - top_scores[min(2, len(top_scores) - 1)]) <= 0.12
    )
    mid_band_count = sum(1 for score in top_scores[:6] if 0.22 <= score <= 0.55)
    reasons: list[str] = []

    if low_diversity:
        reasons.append("low_domain_diversity")
    if payloads is None:
        if clustered_scores:
            reasons.append("clustered_scores")
        if mid_band_count >= 3:
            reasons.append("mid_confidence_cluster")

    parsed_count = 0
    parse_ratio = 0.0
    trusted_count = 0
    if payloads is not None:
        preview_window = min(profile.preview_fetch_limit, len(payloads))
        top_payloads = payloads[:preview_window]
        parsed_count = sum(1 for payload in top_payloads if payload.text)
        parse_ratio = (parsed_count / max(1, preview_window)) if preview_window else 0.0
        trusted_count = sum(
            1 for result in top_results[:4]
            if (result.trust_tier or "?") in {"A", "B", "friendly", "moderate"}
        )
        if parsed_count <= 2:
            reasons.append("sparse_previews")
        elif parse_ratio < 0.5:
            reasons.append("low_preview_ratio")

        # Strong technical evidence already present — don't widen just because
        # the query is technical.
        if parsed_count >= 4 and trusted_count >= 2 and not low_diversity and not clustered_scores:
            meta.update(
                {
                    "domain_diversity": domain_diversity,
                    "parsed_count": parsed_count,
                    "parse_ratio": round(parse_ratio, 3),
                    "trusted_count": trusted_count,
                    "reasons": reasons,
                }
            )
            return base_profile, meta

    if not reasons:
        meta.update(
            {
                "domain_diversity": domain_diversity,
                "parsed_count": parsed_count,
                "parse_ratio": round(parse_ratio, 3),
                "trusted_count": trusted_count,
                "reasons": reasons,
            }
        )
        return base_profile, meta

    growth = 2 if primary == "technical" else 1
    profile.max_results = max(
        base_profile.max_results,
        min(max(profile.max_results, base_profile.max_results) + growth, 10),
    )
    if payloads is None:
        profile.preview_fetch_limit = max(
            base_profile.preview_fetch_limit,
            min(
                max(profile.preview_fetch_limit, base_profile.preview_fetch_limit) + 1,
                7,
            ),
        )
    profile.unparsed_bonus = max(
        base_profile.unparsed_bonus,
        min(max(profile.unparsed_bonus, base_profile.unparsed_bonus) + 1, 3),
    )
    profile.min_score_unparsed = max(0.20, min(profile.min_score_unparsed, base_profile.min_score_unparsed) - 0.05)

    meta.update(
        {
            "applied": True,
            "domain_diversity": domain_diversity,
            "parsed_count": parsed_count,
            "parse_ratio": round(parse_ratio, 3),
            "trusted_count": trusted_count,
            "reasons": reasons,
        }
    )
    return profile, meta


_DOWNLOADABLE_EXTS = (".pdf", ".mp4", ".mp3", ".docx", ".xlsx", ".csv")


# Short badge label for result URL type (VIDEO, PDF, WIKI, etc.).
def _badge_type(url: str) -> str:
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "VIDEO"
    if ".pdf" in u or "/pdf/" in u:
        return "PDF"
    if "wikipedia.org" in u:
        return "WIKI"
    if "github.com" in u:
        return "GITHUB"
    if "arxiv.org" in u:
        return "ARXIV"
    if any(u.endswith(ext) for ext in _DOWNLOADABLE_EXTS):
        return "FILE"
    return "WEB"


# Resolve direct PDF URL from result metadata or arxiv abs link.
def _infer_pdf_url(result: SearchResult) -> str:
    current = str(result.pdf_url or "").strip()
    if current:
        return current

    url = str(result.url or "").strip()
    if not url:
        return ""
    if looks_like_pdf_url(url):
        return url
    if "arxiv.org/abs/" in url:
        return url.replace("/abs/", "/pdf/", 1)
    return ""


# Populate pdf_url on each SearchResult when inferable.
def _enrich_pdf_urls(results: list[SearchResult]) -> list[SearchResult]:
    for result in results:
        result.pdf_url = _infer_pdf_url(result)
    return results


# Human-readable search engine / provider label for output.
def _badge_engine(engine: str) -> str:
    e = engine.lower()
    if e.startswith("academic:"):
        provider = e[len("academic:"):]
        return provider.split(".", 1)[0].replace("-", "").capitalize()
    if "yandex" in e:
        return "Yandex"
    # hosted:tavily / hosted:brave / hosted:bing / hosted:serpapi
    if e.startswith("hosted:"):
        provider = e[len("hosted:"):]
        return provider.capitalize()
    if "brave" in e:
        return "Brave"
    if "bing" in e:
        return "Bing"
    return "DDGS"


# Collapse whitespace and truncate text for snippet/preview display.
def _display_text(text: str, limit: int) -> str:
    compact = " ".join((text or "").split()).strip(" ,;:|-")
    if not compact:
        return ""
    return compact[:limit].rstrip(" ,;:|-")


# Token Jaccard + char similarity for snippet/preview de-duplication.
def _semantic_duplicate_ratio(a: str, b: str) -> float:
    left = " ".join((a or "").lower().split())
    right = " ".join((b or "").lower().split())
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0

    left_tokens = set(re.findall(r"\w+", left, flags=re.UNICODE))
    right_tokens = set(re.findall(r"\w+", right, flags=re.UNICODE))
    token_jaccard = 0.0
    if left_tokens and right_tokens:
        token_jaccard = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))

    from difflib import SequenceMatcher
    char_ratio = SequenceMatcher(None, left, right).ratio()
    return max(token_jaccard, char_ratio)


# Drop preview text that largely duplicates the SERP snippet.
def _dedupe_preview_against_snippet(snippet: str, preview: str, threshold: float = 0.92) -> str:
    if not preview:
        return ""
    if not snippet:
        return preview
    return "" if _semantic_duplicate_ratio(snippet, preview) >= threshold else preview


# Normalized host from URL for display and favicons.
def _source_domain(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host.removeprefix("www.")


# Short display label from domain (e.g. github.com → Github).
def _display_domain(domain: str) -> str:
    parts = [p for p in (domain or "").split(".") if p]
    if len(parts) >= 2:
        label = parts[-2]
    elif parts:
        label = parts[0]
    else:
        return ""
    return label.replace("-", " ").title()


# DuckDuckGo favicon URL for a domain.
def _favicon_url(domain: str) -> str:
    return f"https://icons.duckduckgo.com/ip3/{domain}.ico" if domain else ""


# Build SearchSource struct from a ranked result and optional preview.
def _source_from_result(
    result: SearchResult,
    rank: int,
    *,
    source_id: str | None = None,
    score: float | None = None,
    preview: str = "",
    snippet_limit: int = 600,
    preview_limit: int = 1600,
) -> SearchSource:
    domain = _source_domain(result.url)
    snippet_text = _display_text(result.snippet or "", snippet_limit)
    preview_text = _display_text(preview or "", preview_limit)
    preview_text = _dedupe_preview_against_snippet(snippet_text, preview_text)
    return SearchSource(
        id=source_id or f"source-{rank}",
        rank=rank,
        title=(result.title or "").strip(),
        url=(result.url or "").strip(),
        domain=domain,
        display_domain=_display_domain(domain) or domain,
        favicon_url=_favicon_url(domain),
        snippet=snippet_text,
        preview=preview_text,
        published_date=_normalize_date(result.published_date) or (result.published_date or ""),
        engine=result.engine or "",
        trust_tier=result.trust_tier or "?",
        score=round(float(score if score is not None else result.score or 0.0), 4),
        pdf_url=_infer_pdf_url(result),
    )


# Citation-oriented context block for the model from SearchSource list.
def _build_model_context(
    query: str,
    sources: list[SearchSource],
    total_char_budget: int = 0,
) -> str:
    lines: list[str] = [
        f"Search results for: {query}",
        "",
        "Citation rules:",
        "- Cite search evidence only with the exact citation handles listed below, for example [cabc-1].",
        "- Put the citation handle immediately after the sentence or bullet it supports.",
        "- Use a handle only when that source's Title, Preview, or Content explicitly supports the claim.",
        "- Do not cite a source because its domain or title merely looks related.",
        "- Do not reuse handles from other searches or earlier tool calls unless they appear in this exact source list.",
        "- Do not invent, renumber, shorten, translate, or combine citation handles.",
        "- Do not write bare domain names, URLs, or source numbers as citations when a handle is available.",
        "- If no listed source supports a claim, say that the search did not confirm it or omit the claim.",
        "- Prefer parsed Content over search-engine Preview. Treat Preview-only sources as weaker evidence.",
        "- The UI renders valid citation handles as compact source chips.",
        "",
        "Sources:",
    ]
    total_chars = len("\n".join(lines))
    for source in sources:
        before_len = len(lines)
        lines.append(f"Citation handle: [{source.id}]")
        evidence_kind = "parsed_content" if source.preview and source.preview != source.snippet else "search_preview_only"
        lines.append(f"Evidence kind: {evidence_kind}")
        lines.append(f"Title: {source.title}")
        lines.append(f"Domain: {source.domain}")
        lines.append(f"URL: {source.url}")
        if source.published_date:
            lines.append(f"Date: {source.published_date}")
        excerpt = source.preview or source.snippet
        if excerpt:
            label = "Content" if source.preview and source.preview != source.snippet else "Preview"
            lines.append(f"{label}: {excerpt}")
        lines.append("")
        block = "\n".join(lines[before_len:])
        if total_char_budget and total_chars + len(block) > total_char_budget:
            del lines[before_len:]
            lines.append("[...additional source context omitted: context budget reached]")
            break
        total_chars += len(block)
    return "\n".join(lines).strip()


# Stable citation handle id for a source rank within a search_id.
def _citation_source_id(search_id: str, rank: int) -> str:
    compact = re.sub(r"[^a-z0-9]+", "", (search_id or "").lower())
    compact = compact.removeprefix("srch")
    namespace = (compact[:3] or "src").ljust(3, "0")
    return f"c{namespace}-{rank}"


# Compact UI chip payload for rich search responses.
def _build_compact_ui(query: str, sources: list[SearchSource], limit: int = 3) -> dict[str, object]:
    visible = sources[: max(0, limit)]
    return {
        "label": f"Searching for {query}",
        "source_chips": [
            {
                "source_id": source.id,
                "domain": source.domain,
                "display_domain": source.domain,
                "favicon_url": source.favicon_url,
            }
            for source in visible
        ],
        "more_count": max(0, len(sources) - len(visible)),
    }


_SHOPPING_SCHEMA_VERSION = "shopping_search.v1"
_SHOPPING_PARSER_VERSION = "strict_price.v1"
_SHOPPING_EFFORT_LIMITS = {
    "low": 4,
    "medium": 7,
    "high": 12,
}
_SHOPPING_WORKER_TIMEOUTS = {
    "low": 3.5,
    "medium": 8.5,
    "high": 11.5,
}


def _shopping_intent_weight(class_mix: list[QueryClassWeight], query_types: list[str]) -> float:
    weights = {item.name: float(item.weight or 0.0) for item in class_mix}
    if query_types and query_types[0] == "shopping":
        return max(1.0, weights.get("shopping", 0.0))
    return weights.get("shopping", 0.0)


def _should_run_shopping_core(class_mix: list[QueryClassWeight], query_types: list[str]) -> bool:
    return _shopping_intent_weight(class_mix, query_types) >= 0.28


def _shopping_limit_for_effort(effort: str, max_results: int) -> int:
    normalized = _normalize_search_effort(effort)
    base = _SHOPPING_EFFORT_LIMITS.get(normalized, _SHOPPING_EFFORT_LIMITS["medium"])
    return max(1, min(base, max(1, int(max_results))))


def _shopping_worker_timeout_for_effort(effort: str) -> float:
    normalized = _normalize_search_effort(effort)
    return _SHOPPING_WORKER_TIMEOUTS.get(normalized, _SHOPPING_WORKER_TIMEOUTS["medium"])


def _shopping_price_line(product: dict[str, Any]) -> str:
    price_text = str(product.get("price_text") or "").strip()
    currency = str(product.get("currency") or "").strip()
    price_value = product.get("price_value")
    if price_text:
        return price_text
    if price_value is not None and currency:
        return f"{currency} {price_value}"
    return ""


def _shopping_source_from_product(product: dict[str, Any], rank: int, source_id: str) -> SearchSource | None:
    url = str(product.get("url") or "").strip()
    title = str(product.get("title") or "").strip()
    if not url or not title:
        return None
    domain = str(product.get("source_domain") or "").strip().lower() or _source_domain(url)
    source = str(product.get("source") or "shopping").strip()
    seller = str(product.get("seller") or "").strip()
    availability = str(product.get("availability") or "").strip()
    lane = str(product.get("lane") or "").strip()
    price = _shopping_price_line(product)
    snippet_parts = [
        f"Price: {price}" if price else "",
        f"Seller: {seller}" if seller else "",
        f"Availability: {availability}" if availability else "",
        f"Source: {source}" if source else "",
    ]
    snippet = ". ".join(part for part in snippet_parts if part)
    preview_parts = [
        f"Parsed shopping product with strict price: {price}" if price else "",
        f"Seller: {seller}" if seller else "",
        f"Availability: {availability}" if availability else "",
        f"Source lane: {lane}" if lane else "",
    ]
    preview = ". ".join(part for part in preview_parts if part)
    return SearchSource(
        id=source_id,
        rank=rank,
        title=title,
        url=url,
        domain=domain,
        display_domain=_display_domain(domain) or domain,
        favicon_url=str(product.get("favicon_url") or ""),
        snippet=_display_text(snippet, 360),
        preview=_display_text(preview, 900),
        published_date="",
        engine=f"shopping:{source}",
        trust_tier="shopping",
        score=round(float(product.get("confidence") or 0.0), 4),
        pdf_url="",
    )


def _shopping_product_json(product: dict[str, Any], citation_id: str, effort: str) -> dict[str, Any]:
    normalized = _normalize_search_effort(effort)
    item = {
        "citation_id": citation_id,
        "parse_status": "price_parsed",
        "title": str(product.get("title") or ""),
        "url": str(product.get("url") or ""),
        "source": str(product.get("source") or ""),
        "source_domain": str(product.get("source_domain") or ""),
        "lane": str(product.get("lane") or ""),
        "price_text": str(product.get("price_text") or ""),
        "price_value": product.get("price_value"),
        "currency": str(product.get("currency") or ""),
        "seller": str(product.get("seller") or ""),
        "availability": str(product.get("availability") or ""),
        "favicon_url": str(product.get("favicon_url") or ""),
        "confidence": float(product.get("confidence") or 0.0),
    }
    if normalized != "low":
        item["rating"] = str(product.get("rating") or "")
        item["review_count"] = product.get("review_count")
        item["snippet"] = _display_text(str(product.get("snippet") or ""), 420 if normalized == "medium" else 900)
    if normalized == "high":
        item["meta"] = product.get("meta") or {}
    return item


def _build_shopping_payload(
    query: str,
    effort: str,
    raw_result: dict[str, Any],
    product_citation_ids: list[str],
) -> dict[str, Any]:
    normalized = _normalize_search_effort(effort)
    products = list(raw_result.get("products") or [])
    product_items = [
        _shopping_product_json(product, citation_id, normalized)
        for product, citation_id in zip(products, product_citation_ids)
        if isinstance(product, dict)
    ]
    payload: dict[str, Any] = {
        "schema_version": _SHOPPING_SCHEMA_VERSION,
        "parser_version": _SHOPPING_PARSER_VERSION,
        "query": query,
        "effort": normalized,
        "partial": bool(raw_result.get("partial", False)),
        "partial_reason": str(raw_result.get("partial_reason") or ""),
        "source_count": len(product_items),
        "products": product_items,
        "mix": raw_result.get("mix") or {},
        "timings": raw_result.get("timings") or {},
    }
    if normalized == "high":
        payload["attempts"] = raw_result.get("attempts") or []
        payload["provider_state"] = raw_result.get("provider_state") or {}
    return payload


def _append_shopping_context(model_context: str, shopping_payload: dict[str, Any]) -> str:
    if not shopping_payload.get("products"):
        return model_context
    shopping_json = json.dumps(shopping_payload, ensure_ascii=False, separators=(",", ":"))
    block = (
        "\n\nShopping structured data (strict JSON; cite prices only with citation_id handles):\n"
        "```json\n"
        f"{shopping_json}\n"
        "```"
    )
    return (model_context + block).strip()


# Serialize SearchRichResult for MCP structuredContent.
def _rich_result_to_dict(result: SearchRichResult) -> dict[str, object]:
    return {
        "query": result.query,
        "search_id": result.search_id,
        "sources": [asdict(source) for source in result.sources],
        "model_context": result.model_context,
        "ui": result.ui,
    }


_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
# Matches "Aug 15,2025", "Aug 15, 2025", "Aug. 15, 2025", "Feb 13, 2025"
_HUMAN_DATE_RE = re.compile(
    r"^([A-Z][a-z]{2})\.?\s+(\d{1,2}),?\s*(\d{4})"
)


# Normalize engine date strings to 'Mon DD, YYYY' (empty if unparseable).
def _normalize_date(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    m = _ISO_DATE_RE.search(raw)
    if m:
        try:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= mo <= 12 and 1 <= d <= 31 and 2000 <= y <= 2100:
                return f"{_MONTH_NAMES[mo - 1]} {d:02d}, {y}"
        except (ValueError, IndexError):
            pass
    # Human-readable: "Aug 15,2025", "Feb 13, 2025", "Aug. 15, 2025"
    m = _HUMAN_DATE_RE.match(raw)
    if m:
        try:
            mon, day, year = m.group(1), int(m.group(2)), int(m.group(3))
            if 1 <= day <= 31 and 2000 <= year <= 2100:
                return f"{mon} {day:02d}, {year}"
        except (ValueError, IndexError):
            pass
    return ""


# Build final MCP text output with depth-first vs breadth-first selection.
def _format_results(
    results: list[SearchResult],
    payloads: list[PreviewPayload],
    query: str,
    query_profile: dict,
    output_profile: _OutputProfile,
    snippet_char_budget: int,
    preview_char_budget: int,
    total_char_budget: int = 0,
    query_type: str = "general",
    query_types: list[str] | None = None,
    rep_store=None,
    max_results_override: int | None = None,
) -> str:
    max_results = max_results_override if max_results_override is not None else output_profile.max_results
    _qtypes = query_types if query_types else [query_type]
    scored: list[tuple[float, int, SearchResult, PreviewPayload]] = []
    for idx, (result, payload) in enumerate(zip(results, payloads)):
        score = _result_score(
            result, payload,
            index=idx, total=len(results),
            query=query, profile=query_profile,
            query_type=_qtypes[0], rep_store=rep_store,
        )
        result.score = score
        try:
            _cache.record_query_source_classes(
                query,
                result.url,
                class_mix_json=json.dumps((result.routing_debug or {}).get("class_mix", {}), ensure_ascii=False),
                content_classes_json=json.dumps(
                    {
                        "snippet": (result.routing_debug or {}).get("snippet_decoder_top", []),
                        "parsed": (result.routing_debug or {}).get("parsed_decoder_top", []),
                    },
                    ensure_ascii=False,
                ),
                snippet_score=float(getattr(result, "snippet_relevance_score", 0.0) or 0.0),
                parsed_score=float(getattr(result, "parsed_relevance_score", 0.0) or 0.0),
            )
        except Exception as _e:
            logger.debug("source class cache write failed url=%s: %s", result.url, _e)
        scored.append((score, idx, result, payload))

        # Record content quality for domains that returned actual content.
        # Only when fetch succeeded (payload.text non-empty) so that fetch
        # failures (anti-bot, network) don't unfairly penalise a domain.
        # Record for every matched query type so reputation is tracked per-type.
        if rep_store is not None and payload.text:
            domain = domain_from_url(result.url)
            if domain:
                signal = _content_quality_signal(payload, result, query)
                for qt in _qtypes:
                    try:
                        rep_store.record(domain, qt, signal)
                    except Exception as _e:
                        logger.debug("rep_store.record failed domain=%s qt=%s: %s", domain, qt, _e)

    # Keep score-based improvements local to the provider's original order.
    scored = _bounded_rerank(scored)

    # Parsed content, lexical match, and quality affect score, but no separate
    # parsed-first pass is allowed to bypass the provider-rank movement cap.
    final = scored[:max_results]

    header = f"Search: {query}\n"
    lines: list[str] = [header]
    total_chars = len(header)

    for rank, (score, _, result, payload) in enumerate(final, 1):
        badge = _badge_type(result.url)
        engine = _badge_engine(result.engine)
        tier = result.trust_tier or "?"
        snippet_text = _display_text(result.snippet or "", snippet_char_budget)
        preview_text = _display_text(payload.text or "", preview_char_budget)

        date_str = _normalize_date(result.published_date)
        block_lines = [f"[{rank}] [{badge}] [{engine}] [{tier}]"]
        block_lines.append("Title  :")
        block_lines.append(result.title)
        block_lines.append("URL    :")
        block_lines.append(result.url)
        if result.pdf_url and result.pdf_url != result.url:
            block_lines.append("PDF URL:")
            block_lines.append(result.pdf_url)
        if date_str:
            block_lines.append(f"Date   : {date_str}")
        if preview_text:
            if snippet_text:
                block_lines.append("Snippet:")
                block_lines.append(snippet_text)
            block_lines.append("Preview:")
            block_lines.append(preview_text)
        elif snippet_text:
            block_lines.append("Preview:")
            block_lines.append(snippet_text)
        block_lines.append("")

        block = "\n".join(block_lines)

        if total_char_budget and total_chars + len(block) > total_char_budget:
            lines.append(f"[...{max_results - rank + 1} result(s) omitted — context budget reached]")
            break

        lines.append(block)
        total_chars += len(block)

    if len(scored) == 0:
        lines.append("No results found.")

    return "\n".join(lines).strip()


# Select rich sources using measured score with bounded provider-rank movement.
def _select_output_sources(
    results: list[SearchResult],
    payloads: list[PreviewPayload],
    query: str,
    *,
    query_profile: _QueryProfile,
    output_profile: _OutputProfile,
    query_type: str = "general",
    query_types: list[str] | None = None,
    rep_store=None,
    max_results_override: int | None = None,
) -> list[tuple[SearchResult, PreviewPayload]]:
    max_results = max_results_override if max_results_override is not None else output_profile.max_results
    _qtypes = query_types if query_types else [query_type]
    scored: list[tuple[float, int, SearchResult, PreviewPayload]] = []
    for idx, (result, payload) in enumerate(zip(results, payloads)):
        score = _result_score(
            result,
            payload,
            index=idx,
            total=len(results),
            query=query,
            profile=query_profile,
            query_type=_qtypes[0],
            rep_store=rep_store,
        )
        result.score = score
        try:
            _cache.record_query_source_classes(
                query,
                result.url,
                class_mix_json=json.dumps((result.routing_debug or {}).get("class_mix", {}), ensure_ascii=False),
                content_classes_json=json.dumps(
                    {
                        "snippet": (result.routing_debug or {}).get("snippet_decoder_top", []),
                        "parsed": (result.routing_debug or {}).get("parsed_decoder_top", []),
                    },
                    ensure_ascii=False,
                ),
                snippet_score=float(getattr(result, "snippet_relevance_score", 0.0) or 0.0),
                parsed_score=float(getattr(result, "parsed_relevance_score", 0.0) or 0.0),
            )
        except Exception as _e:
            logger.debug("source class cache write failed url=%s: %s", result.url, _e)
        scored.append((score, idx, result, payload))

    final = _bounded_rerank(scored)[:max_results]

    return [(result, payload) for _, _, result, payload in final]


@dataclass
class WebSearchOptions:
    max_results: int = 10
    fetch_previews: bool = True
    total_context_budget: Optional[int] = None
    candidate_pool_multiplier: Optional[int] = None
    ddgs_hedge_count: Optional[int] = None
    ddgs_worker_timeout: Optional[float] = None
    ddgs_engine_timeout: Optional[int] = None
    ddgs_max_retries: Optional[int] = None
    use_hosted_engines: bool = True
    use_fast_academic: bool = True
    concurrency: int = 4
    fetch_timeout: float = 6.0
    total_timeout: float = 12.0
    timelimit: Optional[str] = None   # DDGS time filter: "d", "w", "m", "y"
    effort: str = "medium"
    effort_multiplier: int = 1


# Orchestrate fast web search across DDGS and hosted search APIs.
class WebSearchService:
    def __init__(self, options: Optional[WebSearchOptions] = None) -> None:
        cfg = load_search_config()
        self._cfg = cfg
        self._opts = options or WebSearchOptions(
            max_results=cfg.search.max_results,
            fetch_timeout=cfg.search.preview_fetch_timeout,
            total_timeout=cfg.search.preview_total_timeout,
        )

    # DDGS + hosted + academic fetch, merge, dedup, triage.
    async def _run_search_pipeline(
        self,
        query: str,
        lang: str,
        query_types: list[str],
        query_type: str,
        out_profile: _OutputProfile,
        opts: WebSearchOptions,
        req_id: str = "-",
        class_mix: list[QueryClassWeight] | None = None,
        source_budget: dict[str, int] | None = None,
        model_session: SearchModelSession | None = None,
    ) -> tuple[list[SearchResult], list]:
        pool_multiplier = max(
            1,
            int(
                opts.candidate_pool_multiplier
                if opts.candidate_pool_multiplier is not None
                else self._cfg.search.candidate_pool_multiplier
            ),
        )
        buffer = max(0, int(self._cfg.search.result_buffer_size))
        fetch_max = out_profile.max_results + buffer

        hosted_engines = available_hosted_engines() if opts.use_hosted_engines else []
        use_fast_academic = opts.use_fast_academic and bool({"academic", "medical"} & set(query_types))
        n_hosted = len(hosted_engines)
        ddgs_multiplier = max(1, pool_multiplier - n_hosted)
        ddgs_hedge = max(
            1,
            int(opts.ddgs_hedge_count)
            if opts.ddgs_hedge_count is not None
            else max(1, 2 - n_hosted),
        )
        hosted_max = fetch_max
        academic_budget = sum((source_budget or {}).get(name, 0) for name in ("academic", "medical"))
        academic_max = min(fetch_max, max(3, academic_budget or 8))

        _trace(req_id, "providers.config",
               n_hosted=n_hosted, ddgs_multiplier=ddgs_multiplier,
               ddgs_hedge=ddgs_hedge, hosted_engines=hosted_engines,
               fast_academic=use_fast_academic)

        ddgs_task = asyncio.create_task(
            async_ddgs_search(
                query,
                max_results=fetch_max * ddgs_multiplier,
                query_type=query_type,
                query_types=query_types,
                lang=lang,
                timelimit=opts.timelimit,
                hedge_count=ddgs_hedge,
                worker_timeout=opts.ddgs_worker_timeout,
                engine_timeout=opts.ddgs_engine_timeout,
                max_retries=opts.ddgs_max_retries,
            )
        )
        hosted_tasks: dict[str, asyncio.Task] = {
            engine: asyncio.create_task(
                async_hosted_search(
                    engine, query, max_results=hosted_max,
                    timelimit=opts.timelimit, query_type=query_type,
                )
            )
            for engine in hosted_engines
        }
        academic_task: asyncio.Task | None = None
        if use_fast_academic:
            academic_fetcher = AcademicFetcher(timeout=min(max(float(opts.fetch_timeout), 4.0), 8.0))
            academic_task = asyncio.create_task(
                academic_fetcher.search_fast(
                    query,
                    max_results=academic_max,
                    topics=[qt for qt in query_types if qt in {"academic", "medical"}],
                )
            )

        provider_t0 = time.perf_counter()
        ddgs_results: list[SearchResult] = await ddgs_task
        hosted_results: dict[str, list[SearchResult]] = {}
        for engine, task in hosted_tasks.items():
            try:
                hosted_results[engine] = await task
            except Exception as exc:
                logger.warning("[hosted:%s] task raised: %s", engine, exc)
                hosted_results[engine] = []
        academic_results: list[SearchResult] = []
        if academic_task is not None:
            try:
                academic_results = await academic_task
            except Exception as exc:
                logger.warning("[academic_fast] task raised: %s", exc)
                academic_results = []

        _trace(req_id, "providers.done",
               elapsed=round(time.perf_counter() - provider_t0, 3),
               ddgs=len(ddgs_results),
               academic_fast=len(academic_results),
               **{f"hosted_{k}": len(v) for k, v in hosted_results.items()})

        merge_t0 = time.perf_counter()
        merged = ddgs_results[:fetch_max * pool_multiplier]
        for h_results in hosted_results.values():
            merged = merged + h_results
        if academic_results:
            merged = merged + academic_results
        merged = merged[: fetch_max * pool_multiplier * 2]
        merged = _enrich_pdf_urls(merged)
        deduped = _apply_domain_cap(_dedup_results(merged))
        effective_mix = class_mix or _build_legacy_class_mix(query)
        _apply_registry_routing(deduped, effective_mix)
        _apply_snippet_decoder(
            deduped, query, model_session, effort=opts.effort, req_id=req_id,
        )
        _trace(req_id, "merge.done",
               elapsed=round(time.perf_counter() - merge_t0, 3),
               merged=len(merged), deduped=len(deduped))

        triage = _triage_results(deduped, query) if deduped else []
        return deduped, triage

    # Build progressively simpler query variants for zero-result fallback.
    @staticmethod
    def _fallback_query_variants(query: str) -> list[str]:
        base = " ".join(str(query or "").split()).strip()
        if not base:
            return []

        variants: list[str] = []

        def add_variant(value: str) -> None:
            normalized = " ".join(str(value or "").split()).strip()
            if normalized and normalized != base and normalized not in variants:
                variants.append(normalized)

        # 1) Remove quotes that can over-constrain DDGS.
        unquoted = re.sub(r"[\"'`]+", " ", base)
        add_variant(unquoted)

        # 2) Strip search operators and site constraints for an open fallback.
        no_ops = re.sub(r"(?<!\S)-?site:[^\s]+", " ", unquoted, flags=re.IGNORECASE)
        no_ops = re.sub(r"(?<!\S)(?:OR|\|)(?=\s|$)", " ", no_ops, flags=re.IGNORECASE)
        no_ops = re.sub(r"(?<!\S)-[^\s]+", " ", no_ops)
        add_variant(no_ops)

        # 3) Keep only core lexical terms (cap length to improve recall).
        core_terms = re.findall(r"[A-Za-z0-9_\-]{2,}|[А-Яа-яЁё0-9_\-]{2,}", no_ops)
        if core_terms:
            add_variant(" ".join(core_terms[:4]))
            add_variant(" ".join(core_terms[:3]))

        return variants

    # Run search pipeline; retry with simpler query variants if empty.
    async def _run_with_zero_result_fallback(
        self,
        *,
        provider_query: str,
        analysis_query: str,
        query_types: list[str],
        out_profile: _OutputProfile,
        opts: WebSearchOptions,
        req_id: str,
        class_mix: list[QueryClassWeight] | None = None,
        source_budget: dict[str, int] | None = None,
        model_session: SearchModelSession | None = None,
    ) -> tuple[list[SearchResult], list[_TriageResult], str]:
        lang = infer_query_language(analysis_query)
        query_type = query_types[0] if query_types else "general"
        deduped, triage = await self._run_search_pipeline(
            provider_query,
            lang,
            query_types,
            query_type,
            out_profile,
            opts,
            req_id,
            class_mix=class_mix,
            source_budget=source_budget,
            model_session=model_session,
        )
        if deduped:
            return deduped, triage, analysis_query
        if _is_low_effort(opts):
            return [], [], analysis_query

        fallback_opts = replace(
            opts,
            max_results=max(5, min(int(opts.max_results), int(self._cfg.effort.zero_result_fallback_max_results))),
            candidate_pool_multiplier=int(self._cfg.effort.zero_result_fallback_candidate_pool_multiplier),
            ddgs_hedge_count=int(self._cfg.effort.low_ddgs_hedge_count),
            ddgs_worker_timeout=min(
                float(opts.ddgs_worker_timeout or self._cfg.effort.medium_ddgs_worker_timeout),
                float(self._cfg.effort.zero_result_fallback_ddgs_worker_timeout),
            ),
            ddgs_engine_timeout=min(
                int(opts.ddgs_engine_timeout or self._cfg.search.ddgs_engine_timeout),
                int(self._cfg.effort.zero_result_fallback_ddgs_engine_timeout),
            ),
            ddgs_max_retries=int(self._cfg.effort.zero_result_fallback_ddgs_max_retries),
            fetch_previews=False,
            use_fast_academic=False,
            effort="medium",
            effort_multiplier=1,
        )
        fallback_profile = _apply_effort_to_output_profile(_get_output_profile(query_types), fallback_opts)

        for index, variant in enumerate(self._fallback_query_variants(analysis_query), start=1):
            variant_lang = infer_query_language(variant)
            variant_types = infer_query_types(variant)
            variant_type = variant_types[0] if variant_types else query_type
            variant_profile = _apply_effort_to_output_profile(_get_output_profile(variant_types), fallback_opts)
            _trace(
                req_id,
                "search.fallback.try",
                index=index,
                variant=variant,
                ddgs_worker_timeout=fallback_opts.ddgs_worker_timeout,
                candidate_pool_multiplier=fallback_opts.candidate_pool_multiplier,
            )
            deduped, triage = await self._run_search_pipeline(
                variant,
                variant_lang,
                variant_types,
                variant_type,
                variant_profile or fallback_profile,
                fallback_opts,
                req_id,
                class_mix=_build_legacy_class_mix(variant),
                source_budget=allocate_source_budget(_build_legacy_class_mix(variant), fallback_profile.max_results),
                model_session=model_session,
            )
            if deduped:
                _trace(req_id, "search.fallback.hit", index=index, variant=variant, count=len(deduped))
                return deduped, triage, variant

        return [], [], analysis_query

    # Run web search and return formatted text for the MCP tool.
    async def search(
        self,
        query: str,
        deadline: float | None = None,
        model_session: SearchModelSession | None = None,
    ) -> str:
        opts = self._opts
        req_id = _make_request_id()
        overall_t0 = time.perf_counter()
        original_query = query
        snippet_char_budget = max(600, int(self._cfg.search.max_snippet_chars))
        preview_char_budget = max(
            int(self._cfg.search.preview_max_chars),
            int(self._cfg.search.max_snippet_chars),
        )
        if _is_low_effort(opts):
            snippet_char_budget = 320
            preview_char_budget = 320
        constraints = parse_domain_constraints(query)
        analysis_query = constraints.clean_query or query
        analysis_query, _ = _apply_year_hint_policy(analysis_query, self._cfg.query)
        provider_query = build_provider_query(original_query, constraints) or analysis_query
        query = analysis_query
        lang = infer_query_language(query)
        class_mix, class_debug = _build_neural_class_mix(query, model_session, effort=opts.effort)
        query_types = _class_mix_to_legacy_types(class_mix)
        query_type = query_types[0]
        query_profile = _parse_query_profile(query)
        out_profile = _apply_effort_to_output_profile(_get_output_profile(query_types), opts)
        source_budget = allocate_source_budget(class_mix, out_profile.max_results)

        # Per-type profile overrides config defaults for fetch depth and output count.
        # preview_fetch_limit: how many pages to scrape (depth-first types scrape more)
        # max_results: passed to _format_results — breadth-first types show more results
        preview_fetch_limit = out_profile.preview_fetch_limit

        logger.info(
            "web_search query=%r lang=%s types=%s profile=max%d/fetch%d/bonus%d",
            query, lang, query_types,
            out_profile.max_results, out_profile.preview_fetch_limit, out_profile.unparsed_bonus,
        )
        _log_neural_usage(
            req_id,
            effort=opts.effort,
            model_session=model_session,
            class_debug=class_debug,
        )
        _trace(
            req_id,
            "search.start",
            query=original_query,
            normalized_query=query,
            provider_query=provider_query,
            lang=lang,
            query_type=query_type,
            query_types=query_types,
            class_mix=[asdict(item) for item in class_mix],
            source_budget=source_budget,
            class_debug=class_debug,
            include_domains=constraints.include_domains,
            exclude_domains=constraints.exclude_domains,
            out_max_results=out_profile.max_results,
            out_preview_fetch_limit=out_profile.preview_fetch_limit,
            out_unparsed_bonus=out_profile.unparsed_bonus,
            fetch_previews=opts.fetch_previews,
            chosen_profile=f"{out_profile.max_results}/{out_profile.preview_fetch_limit}/{out_profile.unparsed_bonus}",
        )

        deduped, triage, effective_query = await self._run_with_zero_result_fallback(
            provider_query=provider_query,
            analysis_query=query,
            query_types=query_types,
            out_profile=out_profile,
            opts=opts,
            req_id=req_id,
            class_mix=class_mix,
            source_budget=source_budget,
            model_session=model_session,
        )
        query = effective_query
        if constraints.has_constraints:
            before = len(deduped)
            deduped = filter_results_by_domain_constraints(deduped, constraints)
            _trace(
                req_id,
                "constraints.filter",
                before=before,
                after=len(deduped),
                include_domains=constraints.include_domains,
                exclude_domains=constraints.exclude_domains,
            )
            triage = _triage_results(deduped, query) if deduped else []

        if not deduped:
            _trace(req_id, "search.empty", elapsed=round(time.perf_counter() - overall_t0, 3))
            if constraints.has_constraints:
                return (
                    f"No results found for: {original_query}\n"
                    f"Applied domain constraints: "
                    f"include={constraints.include_domains or ['*']} "
                    f"exclude={constraints.exclude_domains or []}"
                )
            return f"No results found for: {original_query}"

        adapted_profile, adapt_meta = _adapt_output_profile(
            deduped,
            triage,
            out_profile,
            query_types=query_types,
        )
        if adapted_profile != out_profile:
            out_profile = _enforce_effort_after_adaptation(adapted_profile, opts)
            preview_fetch_limit = out_profile.preview_fetch_limit
            _trace(
                req_id,
                "profile.adapt.pre",
                out_max_results=out_profile.max_results,
                out_preview_fetch_limit=out_profile.preview_fetch_limit,
                out_unparsed_bonus=out_profile.unparsed_bonus,
                reasons=list(adapt_meta.get("reasons", [])),
                domain_diversity=adapt_meta.get("domain_diversity"),
                trigger_reason=";".join(list(adapt_meta.get("reasons", []))),
                chosen_top_k=out_profile.max_results,
            )

        skipped_count = sum(1 for t in triage if t.skip)
        race_count = sum(1 for t in triage if not t.skip and t.fetch_policy == "race")
        _trace(req_id, "triage.done",
               skipped=skipped_count, race=race_count,
               cheap=len(triage) - skipped_count - race_count, total=len(triage))
        if skipped_count or race_count:
            logger.debug("triage: skipped=%d race=%d cheap=%d (total=%d)",
                         skipped_count, race_count, len(triage) - skipped_count - race_count, len(triage))

        # Build ordered fetch candidate list: non-skipped, up to preview_fetch_limit
        to_fetch: list[SearchResult] = []
        to_fetch_indices: list[int] = []
        to_fetch_policies: list[str] = []
        for i, (result, tr) in enumerate(zip(deduped, triage)):
            if not tr.skip and len(to_fetch) < preview_fetch_limit:
                to_fetch.append(result)
                to_fetch_indices.append(i)
                to_fetch_policies.append(tr.fetch_policy)
        _trace(
            req_id,
            "fetch_plan.done",
            to_fetch=len(to_fetch),
            policies=to_fetch_policies[:],
        )

        # -- Preview fetching --
        loop = asyncio.get_running_loop()
        payloads: list[PreviewPayload] = [PreviewPayload()] * len(deduped)

        if to_fetch and opts.fetch_previews and self._cfg.search.auto_scrape_preview:
            preview_settings = _configure_preview_settings(
                get_preview_settings(apply_hardware_profile=False),
                query_type=query_type,
            )
            fetched = await _fetch_previews(
                to_fetch,
                query=query,
                concurrency=opts.concurrency,
                fetch_timeout=opts.fetch_timeout,
                total_timeout=opts.total_timeout,
                preview_settings=preview_settings,
                loop=loop,
                policies=to_fetch_policies,
                early_return_threshold=(
                    0
                    if _normalize_search_effort(opts.effort) == "high"
                    else max(0, int(self._cfg.search.early_return_threshold))
                ),
                req_id=req_id,
                deadline=deadline,
            )
            for i, payload in zip(to_fetch_indices, fetched):
                payloads[i] = payload
        _apply_parsed_decoder(
            deduped, payloads, query, model_session, effort=opts.effort, req_id=req_id,
        )

        adapted_post_profile, post_meta = _adapt_output_profile(
            deduped,
            triage,
            out_profile,
            query_types=query_types,
            payloads=payloads,
        )
        if adapted_post_profile != out_profile:
            out_profile = _enforce_effort_after_adaptation(adapted_post_profile, opts)
            _trace(
                req_id,
                "profile.adapt.post",
                out_max_results=out_profile.max_results,
                out_preview_fetch_limit=out_profile.preview_fetch_limit,
                out_unparsed_bonus=out_profile.unparsed_bonus,
                reasons=list(post_meta.get("reasons", [])),
                parsed_count=post_meta.get("parsed_count"),
                parse_ratio=post_meta.get("parse_ratio"),
                domain_diversity=post_meta.get("domain_diversity"),
                trigger_reason=";".join(list(post_meta.get("reasons", []))),
                chosen_top_k=out_profile.max_results,
            )

        # -- Background prefetch of non-displayed buffer results --
        # Candidates: non-skipped results that didn't make the preview_fetch_limit
        # cut, and whose URLs are not already fresh in the source cache.
        # Runs as a fire-and-forget task — never blocks the response.
        if opts.fetch_previews and self._cfg.search.auto_scrape_preview:
            fetched_urls = {r.url for r in to_fetch}
            prefetch_candidates = [
                r.url
                for r, tr in zip(deduped, triage)
                if r.url not in fetched_urls and not tr.skip
            ][:_PREFETCH_MAX_URLS]
            if prefetch_candidates:
                asyncio.create_task(
                    _prefetch_urls_background(prefetch_candidates, req_id=req_id)
                )
                _trace(req_id, "prefetch.scheduled", urls=len(prefetch_candidates))

        format_t0 = time.perf_counter()
        try:
            _rep_store = get_reputation_store()
        except Exception as _e:
            logger.debug("reputation_store unavailable: %s", _e)
            _rep_store = None

        result_text = _format_results(
            deduped, payloads, original_query,
            query_profile=query_profile,
            output_profile=out_profile,
            snippet_char_budget=snippet_char_budget,
            preview_char_budget=preview_char_budget,
            total_char_budget=(
                opts.total_context_budget
                if opts.total_context_budget is not None
                else self._cfg.search.total_context_budget
            ),
            query_type=query_type,
            query_types=query_types,
            rep_store=_rep_store,
            max_results_override=min(out_profile.max_results, opts.max_results),
        )
        _trace(
            req_id,
            "format.done",
            elapsed=round(time.perf_counter() - format_t0, 3),
            output_chars=len(result_text),
            payload_nonempty=sum(1 for p in payloads if p.text),
        )
        _trace(req_id, "search.done", elapsed=round(time.perf_counter() - overall_t0, 3))
        return result_text

    # Deep-research entry: ranked SearchResult list without preview formatting.
    async def search_structured(
        self,
        query: str,
        deadline: float | None = None,
        model_session: SearchModelSession | None = None,
    ) -> list[SearchResult]:
        opts = self._opts
        constraints = parse_domain_constraints(query)
        analysis_query = constraints.clean_query or query
        analysis_query, _ = _apply_year_hint_policy(analysis_query, self._cfg.query)
        provider_query = build_provider_query(query, constraints) or analysis_query
        query = analysis_query
        lang = infer_query_language(query)
        class_mix, _class_debug = _build_neural_class_mix(query, model_session, effort=opts.effort)
        query_types = _class_mix_to_legacy_types(class_mix)
        query_type = query_types[0]
        out_profile = _apply_effort_to_output_profile(_get_output_profile(query_types), opts)

        req_id = _make_request_id()
        deduped, triage, effective_query = await self._run_with_zero_result_fallback(
            provider_query=provider_query,
            analysis_query=query,
            query_types=query_types,
            out_profile=out_profile,
            opts=opts,
            req_id=req_id,
            class_mix=class_mix,
            source_budget=allocate_source_budget(class_mix, out_profile.max_results),
            model_session=model_session,
        )
        query = effective_query
        if constraints.has_constraints:
            deduped = filter_results_by_domain_constraints(deduped, constraints)
            triage = _triage_results(deduped, query) if deduped else []
        if not deduped:
            return []

        adapted_profile, adapt_meta = _adapt_output_profile(
            deduped,
            triage,
            out_profile,
            query_types=query_types,
        )
        if adapted_profile != out_profile:
            out_profile = _enforce_effort_after_adaptation(adapted_profile, opts)
            _trace(
                req_id,
                "structured.profile.adapt",
                trigger_reason=";".join(list(adapt_meta.get("reasons", []))),
                chosen_profile=f"{out_profile.max_results}/{out_profile.preview_fetch_limit}/{out_profile.unparsed_bonus}",
                chosen_top_k=out_profile.max_results,
            )

        scored_structured: list[tuple[float, int, SearchResult, PreviewPayload]] = []
        skipped_count = 0
        for index, (result, tr) in enumerate(zip(deduped, triage)):
            result.score = tr.score
            result.method_hint = tr.fetch_policy
            if tr.skip:
                skipped_count += 1
            scored_structured.append((tr.score, index, result, PreviewPayload()))

        combined = [
            result
            for _, _, result, _ in _bounded_rerank(scored_structured)
        ]
        top_k = _effective_output_limit(out_profile, opts)
        _trace(
            req_id,
            "structured.done",
            chosen_top_k=top_k,
            skipped=skipped_count,
            ranked=len(combined) - skipped_count,
        )
        return combined[:top_k]

    # Structured payload for MCP structuredContent / UI clients.
    async def search_rich(
        self,
        query: str,
        deadline: float | None = None,
        model_session: SearchModelSession | None = None,
    ) -> SearchRichResult:
        opts = self._opts
        search_id = f"srch_{_make_request_id()}"
        req_id = search_id

        # --- 1. Query normalisation (mirrors search() / search_structured()) ---
        constraints = parse_domain_constraints(query)
        analysis_query = constraints.clean_query or query
        analysis_query, _ = _apply_year_hint_policy(analysis_query, self._cfg.query)
        provider_query = build_provider_query(query, constraints) or analysis_query
        query = analysis_query
        lang = infer_query_language(query)
        class_mix, class_debug = _build_neural_class_mix(query, model_session, effort=opts.effort)
        query_types = _class_mix_to_legacy_types(class_mix)
        query_type = query_types[0]
        source_budget = allocate_source_budget(class_mix, opts.max_results)
        query_profile = _parse_query_profile(query)
        out_profile = _apply_effort_to_output_profile(_get_output_profile(query_types), opts)
        preview_fetch_limit = out_profile.preview_fetch_limit
        effort = _normalize_search_effort(opts.effort)
        shopping_task: asyncio.Task[dict[str, Any]] | None = None
        _log_neural_usage(
            req_id,
            effort=opts.effort,
            model_session=model_session,
            class_debug=class_debug,
        )
        if _should_run_shopping_core(class_mix, query_types):
            shopping_limit = _shopping_limit_for_effort(effort, opts.max_results)
            shopping_task = asyncio.create_task(
                async_shopping_search_worker(
                    provider_query,
                    effort=effort,
                    limit=shopping_limit,
                    language=lang,
                    worker_timeout=_shopping_worker_timeout_for_effort(effort),
                )
            )
            _trace(req_id, "shopping.worker.started", limit=shopping_limit, effort=effort, language=lang)

        # --- 2. Provider fetch → merge → dedup → triage ---
        deduped, triage, effective_query = await self._run_with_zero_result_fallback(
            provider_query=provider_query,
            analysis_query=query,
            query_types=query_types,
            out_profile=out_profile,
            opts=opts,
            req_id=req_id,
            class_mix=class_mix,
            source_budget=source_budget,
            model_session=model_session,
        )
        query = effective_query
        if constraints.has_constraints:
            deduped = filter_results_by_domain_constraints(deduped, constraints)
            triage = _triage_results(deduped, query) if deduped else []

        if not deduped:
            shopping_raw: dict[str, Any] = {}
            if shopping_task is not None:
                with contextlib.suppress(Exception):
                    shopping_raw = await shopping_task
            shopping_sources: list[SearchSource] = []
            product_citation_ids: list[str] = []
            shopping_products = [
                product for product in list(shopping_raw.get("products") or [])
                if isinstance(product, dict)
            ]
            for product in shopping_products:
                rank = len(shopping_sources) + 1
                source_id = _citation_source_id(search_id, rank)
                source = _shopping_source_from_product(product, rank, source_id)
                if source is None:
                    continue
                product_citation_ids.append(source_id)
                shopping_sources.append(source)
            if shopping_sources:
                shopping_payload = _build_shopping_payload(query, effort, shopping_raw, product_citation_ids)
                model_context = _append_shopping_context(
                    _build_model_context(query, shopping_sources, total_char_budget=opts.total_context_budget or 0),
                    shopping_payload,
                )
                _trace(req_id, "rich.done", sources=len(shopping_sources), shopping_sources=len(shopping_sources))
                return SearchRichResult(
                    query=query,
                    search_id=search_id,
                    sources=shopping_sources,
                    model_context=model_context,
                    ui={
                        "status": "done",
                        "result_count": len(shopping_sources),
                        "compact": _build_compact_ui(query, shopping_sources),
                        "shopping": shopping_payload,
                    },
                )
            return SearchRichResult(
                query=query,
                search_id=search_id,
                sources=[],
                model_context=f"No results found for: {query}",
                ui={"status": "done", "result_count": 0, "compact": _build_compact_ui(query, [])},
            )

        # --- 3. Pre-fetch adaptive profile (may update preview_fetch_limit) ---
        adapted_profile, adapt_meta = _adapt_output_profile(
            deduped, triage, out_profile, query_types=query_types,
        )
        if adapted_profile != out_profile:
            out_profile = _enforce_effort_after_adaptation(adapted_profile, opts)
            preview_fetch_limit = out_profile.preview_fetch_limit  # keep in sync!
            _trace(
                req_id, "rich.profile.adapt.pre",
                trigger_reason=";".join(list(adapt_meta.get("reasons", []))),
                chosen_profile=f"{out_profile.max_results}/{out_profile.preview_fetch_limit}/{out_profile.unparsed_bonus}",
            )

        skipped_count = sum(1 for t in triage if t.skip)
        race_count = sum(1 for t in triage if not t.skip and t.fetch_policy == "race")
        _trace(req_id, "rich.triage.done",
               skipped=skipped_count, race=race_count,
               cheap=len(triage) - skipped_count - race_count, total=len(triage))

        # --- 4. Triage-aware fetch candidate list ---
        # Only fetch pages where triage said skip=False, up to preview_fetch_limit.
        to_fetch: list[SearchResult] = []
        to_fetch_indices: list[int] = []
        to_fetch_policies: list[str] = []
        for i, (result, tr) in enumerate(zip(deduped, triage)):
            if not tr.skip and len(to_fetch) < preview_fetch_limit:
                to_fetch.append(result)
                to_fetch_indices.append(i)
                to_fetch_policies.append(tr.fetch_policy)
        _trace(req_id, "rich.fetch_plan.done", to_fetch=len(to_fetch), policies=to_fetch_policies[:])

        # --- 5. Preview fetching ---
        loop = asyncio.get_running_loop()
        payloads: list[PreviewPayload] = [PreviewPayload()] * len(deduped)

        if to_fetch and opts.fetch_previews and self._cfg.search.auto_scrape_preview:
            preview_settings = _configure_preview_settings(
                get_preview_settings(apply_hardware_profile=False),
                query_type=query_type,
            )
            fetched = await _fetch_previews(
                to_fetch,
                query=query,
                concurrency=opts.concurrency,
                fetch_timeout=opts.fetch_timeout,
                total_timeout=opts.total_timeout,
                preview_settings=preview_settings,
                loop=loop,
                policies=to_fetch_policies,
                early_return_threshold=(
                    0
                    if _normalize_search_effort(opts.effort) == "high"
                    else max(0, int(self._cfg.search.early_return_threshold))
                ),
                req_id=req_id,
                deadline=deadline,
            )
            for i, payload in zip(to_fetch_indices, fetched):
                payloads[i] = payload
        _apply_parsed_decoder(
            deduped, payloads, query, model_session, effort=opts.effort, req_id=req_id,
        )

        # --- 6. Post-fetch adaptive profile ---
        adapted_post, post_meta = _adapt_output_profile(
            deduped, triage, out_profile, query_types=query_types, payloads=payloads,
        )
        if adapted_post != out_profile:
            out_profile = _enforce_effort_after_adaptation(adapted_post, opts)
            _trace(
                req_id, "rich.profile.adapt.post",
                trigger_reason=";".join(list(post_meta.get("reasons", []))),
                parsed_count=post_meta.get("parsed_count"),
                parse_ratio=post_meta.get("parse_ratio"),
                chosen_profile=f"{out_profile.max_results}/{out_profile.preview_fetch_limit}/{out_profile.unparsed_bonus}",
            )

        # --- 7. Background prefetch (fire-and-forget, does not block response) ---
        if opts.fetch_previews and self._cfg.search.auto_scrape_preview:
            fetched_urls = {r.url for r in to_fetch}
            prefetch_candidates = [
                r.url
                for r, tr in zip(deduped, triage)
                if r.url not in fetched_urls and not tr.skip
            ][:_PREFETCH_MAX_URLS]
            if prefetch_candidates:
                asyncio.create_task(
                    _prefetch_urls_background(prefetch_candidates, req_id=req_id)
                )
                _trace(req_id, "rich.prefetch.scheduled", urls=len(prefetch_candidates))

        # --- 9. Build sources and return ---
        top_k = _effective_output_limit(out_profile, opts)
        try:
            _rep_store = get_reputation_store()
        except Exception as _e:
            logger.debug("reputation_store unavailable: %s", _e)
            _rep_store = None

        selected_sources = _select_output_sources(
            deduped,
            payloads,
            query,
            query_profile=query_profile,
            output_profile=out_profile,
            query_type=query_type,
            query_types=query_types,
            rep_store=_rep_store,
            max_results_override=top_k,
        )

        low_effort = _is_low_effort(opts)
        preview_cap = _preview_display_limit(query_type, low_effort=low_effort)
        sources = [
            _source_from_result(
                result,
                rank,
                source_id=_citation_source_id(search_id, rank),
                score=result.score,
                preview=payload.text,
                snippet_limit=320 if low_effort else 600,
                preview_limit=preview_cap,
            )
            for rank, (result, payload) in enumerate(selected_sources, 1)
        ]
        shopping_raw: dict[str, Any] = {}
        shopping_payload: dict[str, Any] = {}
        if shopping_task is not None:
            with contextlib.suppress(Exception):
                shopping_raw = await shopping_task
            shopping_products = [
                product for product in list(shopping_raw.get("products") or [])
                if isinstance(product, dict)
            ]
            shopping_product_citation_ids: list[str] = []
            shopping_sources: list[SearchSource] = []
            for product in shopping_products:
                rank = len(sources) + len(shopping_sources) + 1
                source_id = _citation_source_id(search_id, rank)
                source = _shopping_source_from_product(product, rank, source_id)
                if source is None:
                    continue
                shopping_product_citation_ids.append(source_id)
                shopping_sources.append(source)
            if shopping_sources:
                sources.extend(shopping_sources)
                shopping_payload = _build_shopping_payload(
                    query,
                    effort,
                    shopping_raw,
                    shopping_product_citation_ids,
                )
                _trace(req_id, "shopping.worker.done", products=len(shopping_sources))
        model_context = _build_model_context(
            query,
            sources,
            total_char_budget=opts.total_context_budget or 0,
        )
        model_context = _append_shopping_context(model_context, shopping_payload)
        _trace(req_id, "rich.done", sources=len(sources), shopping_sources=shopping_payload.get("source_count", 0))
        return SearchRichResult(
            query=query,
            search_id=search_id,
            sources=sources,
            model_context=model_context,
            ui={
                "status": "done",
                "result_count": len(sources),
                "compact": _build_compact_ui(query, sources),
                "shopping": shopping_payload,
            },
        )


# Hard wall-clock limit for the entire search lifecycle.
# When exceeded, the coroutine is cancelled → subprocesses are killed via
# their finally blocks in async_ddgs_search(), aiohttp sessions are closed
# by their async context managers, and executor threads run to natural
# completion (they have internal timeouts so they won't hang indefinitely).
# Short timeout budget for degraded fallback attempts after hard timeout.
def _fallback_timeout_window(hard_timeout: float) -> float:
    effort_cfg = load_search_config().effort
    try:
        base = float(hard_timeout)
    except (TypeError, ValueError):
        base = effort_cfg.medium_hard_timeout
    return max(
        float(effort_cfg.timeout_fallback_min_window),
        min(
            float(effort_cfg.timeout_fallback_max_window),
            base * float(effort_cfg.timeout_fallback_fraction),
        ),
    )


# Compact snippet-only fallback text after search timeout.
def _format_timeout_fallback_text(query: str, results: list[SearchResult], limit: int = 5) -> str:
    if not results:
        return f"Search timed out with no fallback results for: {query}"
    lines: list[str] = [
        f"Search timed out. Returning fallback snippet results for: {query}",
        "",
    ]
    for idx, item in enumerate(results[: max(1, limit)], 1):
        title = (item.title or item.url or "Untitled source").strip()
        domain = domain_from_url(item.url)
        snippet = _display_text(item.snippet or "", 320)
        lines.append(f"[{idx}] {title}")
        if domain:
            lines.append(f"Domain: {domain}")
        if item.url:
            lines.append(f"URL: {item.url}")
        if snippet:
            lines.append(f"Snippet: {snippet}")
        lines.append("")
    return "\n".join(lines).strip()


# Rich JSON payload when search times out but snippet fallback succeeded.
def _timeout_fallback_rich_payload(query: str, results: list[SearchResult]) -> dict[str, object]:
    search_id = f"srch_{_make_request_id()}"
    fallback_sources = [
        _source_from_result(
            result,
            rank,
            source_id=_citation_source_id(search_id, rank),
            score=result.score,
            preview="",
        )
        for rank, result in enumerate(results, 1)
    ]
    model_context = _build_model_context(query, fallback_sources)
    return {
        "query": query,
        "search_id": search_id,
        "sources": [asdict(source) for source in fallback_sources],
        "model_context": model_context,
        "ui": {
            "status": "done",
            "result_count": len(fallback_sources),
            "degraded": True,
            "compact": _build_compact_ui(query, fallback_sources),
        },
    }


# Rich JSON payload for BAD_QUERY validation rejections.
def _rejected_search_payload(query: str, rejection: str) -> dict[str, object]:
    return {
        "query": query,
        "search_id": f"rejected_{_make_request_id()}",
        "sources": [],
        "model_context": rejection,
        "ui": {
            "status": "rejected",
            "result_count": 0,
            "compact": {
                "label": f"Query rejected: {query}",
                "source_chips": [],
                "more_count": 0,
            },
        },
    }


# Wall-clock limit for a search from effort tier or explicit override.
def _effort_hard_timeout(effort: str, hard_timeout: float | None) -> float:
    if hard_timeout is not None:
        return float(hard_timeout)
    effort_cfg = load_search_config().effort
    if effort == "low":
        return float(effort_cfg.low_hard_timeout)
    if effort == "high":
        return float(effort_cfg.high_hard_timeout)
    return float(effort_cfg.medium_hard_timeout)


# WebSearchOptions tuned for low/medium/high effort from config.
def _build_effort_options(
    cfg: object,
    *,
    effort: str | None,
    max_results: int,
    fetch_previews: bool,
    timelimit: Optional[str],
) -> WebSearchOptions:
    resolved_effort = _normalize_search_effort(effort)
    effort_cfg = cfg.effort
    if resolved_effort == "low":
        return WebSearchOptions(
            max_results=max(1, min(int(max_results), int(effort_cfg.low_max_results))),
            fetch_previews=False,
            total_context_budget=int(effort_cfg.low_total_context_budget),
            candidate_pool_multiplier=int(effort_cfg.low_candidate_pool_multiplier),
            ddgs_hedge_count=int(effort_cfg.low_ddgs_hedge_count),
            ddgs_worker_timeout=float(effort_cfg.low_ddgs_worker_timeout),
            ddgs_engine_timeout=int(effort_cfg.low_ddgs_engine_timeout),
            ddgs_max_retries=int(effort_cfg.low_ddgs_max_retries),
            use_hosted_engines=False,
            use_fast_academic=False,
            fetch_timeout=float(effort_cfg.low_preview_fetch_timeout),
            total_timeout=float(effort_cfg.low_preview_total_timeout),
            timelimit=timelimit,
            effort=resolved_effort,
        )
    if resolved_effort == "high":
        multiplier = max(1, int(effort_cfg.high_multiplier))
        return WebSearchOptions(
            max_results=max(1, int(max_results)) * multiplier,
            fetch_previews=fetch_previews,
            total_context_budget=max(1, int(getattr(cfg.search, "total_context_budget", 40_000)))
            * multiplier,
            candidate_pool_multiplier=max(
                1,
                int(getattr(cfg.search, "candidate_pool_multiplier", 2))
                * multiplier,
            ),
            ddgs_worker_timeout=float(effort_cfg.high_ddgs_worker_timeout),
            fetch_timeout=float(effort_cfg.high_preview_fetch_timeout),
            total_timeout=float(effort_cfg.high_preview_total_timeout),
            timelimit=timelimit,
            effort=resolved_effort,
            effort_multiplier=multiplier,
        )
    return WebSearchOptions(
        max_results=max_results,
        fetch_previews=fetch_previews,
        ddgs_worker_timeout=float(effort_cfg.medium_ddgs_worker_timeout),
        fetch_timeout=float(effort_cfg.medium_preview_fetch_timeout),
        total_timeout=float(effort_cfg.medium_preview_total_timeout),
        timelimit=timelimit,
        effort=resolved_effort,
    )


# MCP/CLI entry: formatted text search with hard timeout and timelimit inference.
async def run_web_search(
    query: str,
    max_results: int = 10,
    fetch_previews: bool = True,
    timelimit: Optional[str] = None,
    time_range: Optional[str] = None,
    hard_timeout: float | None = None,
    effort: str = "medium",
) -> str:
    init_t0 = time.perf_counter()
    cfg = load_search_config()
    constraints = parse_domain_constraints(query)
    query_for_search = constraints.clean_query or query
    query_for_search, year_tl = _apply_year_hint_policy(query_for_search, cfg.query)
    rejection = validate_search_query(query_for_search)
    if rejection:
        return rejection
    # Type-based timelimit is disabled when the query explicitly anchors an older year.
    type_tl = _resolve_auto_timelimit(query_for_search)
    # Use the more restrictive of the two signals.
    auto_timelimit = _stricter_timelimit(year_tl, type_tl)
    explicit_timelimit = (
        _normalize_time_range(time_range)
        or _normalize_time_range(timelimit)
        or timelimit
    )
    resolved_timelimit = explicit_timelimit or auto_timelimit
    search_effort = _normalize_search_effort(effort)
    effective_hard_timeout = _effort_hard_timeout(search_effort, hard_timeout)
    opts = _build_effort_options(
        cfg,
        effort=search_effort,
        max_results=max_results,
        fetch_previews=fetch_previews,
        timelimit=resolved_timelimit,
    )
    service = WebSearchService(options=opts)
    trace_logger.info(
        "stage=service.init query=%r elapsed=%.3f",
        query_for_search[:160],
        time.perf_counter() - init_t0,
    )
    try:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + effective_hard_timeout
        with _search_model_session_scope(effort=search_effort) as model_session:
            result_text = await asyncio.wait_for(
                service.search(query, deadline=deadline, model_session=model_session),
                timeout=effective_hard_timeout,
            )
        return result_text
    except asyncio.TimeoutError:
        elapsed = round(time.perf_counter() - init_t0, 1)
        logger.warning(
            "web_search.hard_timeout query=%r elapsed=%.1fs limit=%.0fs",
            query[:80], elapsed, effective_hard_timeout,
        )
        if search_effort == "low":
            return (
                f"Search timed out after {elapsed}s (limit {effective_hard_timeout:.0f}s) "
                f"for: {query_for_search}"
            )
        try:
            fallback_results = await run_web_search_structured(
                query=query,
                max_results=max(3, min(max_results, 8)),
                timelimit=timelimit,
                hard_timeout=_fallback_timeout_window(effective_hard_timeout),
                time_range=time_range,
                effort="low",
            )
        except Exception as fallback_exc:
            logger.warning("web_search.timeout_fallback_failed query=%r err=%s", query[:80], fallback_exc)
            fallback_results = []
        if fallback_results:
            return _format_timeout_fallback_text(query_for_search, fallback_results, limit=max_results)
        return (
            f"Search timed out after {elapsed}s (limit {effective_hard_timeout:.0f}s) "
            f"for: {query_for_search}"
        )


# Structured search returning ranked SearchResult items (no preview formatting).
async def run_web_search_structured(
    query: str,
    max_results: int = 10,
    timelimit: Optional[str] = None,
    hard_timeout: float | None = None,
    time_range: Optional[str] = None,
    effort: str = "medium",
) -> list[SearchResult]:
    cfg = load_search_config()
    constraints = parse_domain_constraints(query)
    query_for_search = constraints.clean_query or query
    query_for_search, year_tl = _apply_year_hint_policy(query_for_search, cfg.query)
    rejection = validate_search_query(query_for_search)
    if rejection:
        return []
    type_tl = _resolve_auto_timelimit(query_for_search)
    auto_timelimit = _stricter_timelimit(year_tl, type_tl)
    explicit_timelimit = (
        _normalize_time_range(time_range)
        or _normalize_time_range(timelimit)
        or timelimit
    )
    resolved_timelimit = explicit_timelimit or auto_timelimit
    search_effort = _normalize_search_effort(effort)
    effective_hard_timeout = _effort_hard_timeout(search_effort, hard_timeout)
    opts = _build_effort_options(
        cfg,
        effort=search_effort,
        max_results=max_results,
        fetch_previews=False,
        timelimit=resolved_timelimit,
    )
    service = WebSearchService(options=opts)
    loop = asyncio.get_event_loop()
    deadline = loop.time() + effective_hard_timeout
    try:
        with _search_model_session_scope(effort=search_effort) as model_session:
            return await asyncio.wait_for(
                service.search_structured(query, deadline=deadline, model_session=model_session),
                timeout=effective_hard_timeout,
            )
    except asyncio.TimeoutError:
        logger.warning(
            "web_search_structured.hard_timeout query=%r limit=%.0fs",
            query[:80], effective_hard_timeout,
        )
        return []


# Rich search payload for MCP structuredContent / UI.
async def run_web_search_rich(
    query: str,
    max_results: int = 10,
    timelimit: Optional[str] = None,
    hard_timeout: float | None = None,
    time_range: Optional[str] = None,
    effort: str = "medium",
) -> dict[str, object]:
    cfg = load_search_config()
    constraints = parse_domain_constraints(query)
    query_for_search = constraints.clean_query or query
    query_for_search, year_tl = _apply_year_hint_policy(query_for_search, cfg.query)
    rejection = validate_search_query(query_for_search)
    if rejection:
        return _rejected_search_payload(query_for_search, rejection)
    type_tl = _resolve_auto_timelimit(query_for_search)
    auto_timelimit = _stricter_timelimit(year_tl, type_tl)
    explicit_timelimit = (
        _normalize_time_range(time_range)
        or _normalize_time_range(timelimit)
        or timelimit
    )
    resolved_timelimit = explicit_timelimit or auto_timelimit
    search_effort = _normalize_search_effort(effort)
    effective_hard_timeout = _effort_hard_timeout(search_effort, hard_timeout)
    opts = _build_effort_options(
        cfg,
        effort=search_effort,
        max_results=max_results,
        fetch_previews=True,
        timelimit=resolved_timelimit,
    )
    service = WebSearchService(options=opts)
    loop = asyncio.get_event_loop()
    deadline = loop.time() + effective_hard_timeout
    try:
        with _search_model_session_scope(effort=search_effort) as model_session:
            rich = await asyncio.wait_for(
                service.search_rich(query.strip(), deadline=deadline, model_session=model_session),
                timeout=effective_hard_timeout,
            )
        return _rich_result_to_dict(rich)
    except asyncio.TimeoutError:
        logger.warning(
            "web_search_rich.hard_timeout query=%r limit=%.0fs",
            query[:80], effective_hard_timeout,
        )
        if search_effort == "low":
            search_id = f"srch_{_make_request_id()}"
            return {
                "query": query_for_search,
                "search_id": search_id,
                "sources": [],
                "model_context": f"Search timed out after {effective_hard_timeout:.0f}s for: {query_for_search}",
                "ui": {
                    "status": "timeout",
                    "result_count": 0,
                    "compact": {
                        "label": f"Searching for {query_for_search}",
                        "source_chips": [],
                        "more_count": 0,
                    },
                },
            }
        fallback_results: list[SearchResult] = []
        try:
            fallback_results = await run_web_search_structured(
                query=query,
                max_results=max(3, min(max_results, 8)),
                timelimit=timelimit,
                hard_timeout=_fallback_timeout_window(effective_hard_timeout),
                time_range=time_range,
                effort="low",
            )
        except Exception as fallback_exc:
            logger.warning("web_search_rich.timeout_fallback_failed query=%r err=%s", query[:80], fallback_exc)

        if fallback_results:
            return _timeout_fallback_rich_payload(query_for_search, fallback_results)

        search_id = f"srch_{_make_request_id()}"
        return {
            "query": query_for_search,
            "search_id": search_id,
            "sources": [],
            "model_context": f"Search timed out after {effective_hard_timeout:.0f}s for: {query_for_search}",
            "ui": {
                "status": "timeout",
                "result_count": 0,
                "compact": {
                    "label": f"Searching for {query_for_search}",
                    "source_chips": [],
                    "more_count": 0,
                },
            },
        }
