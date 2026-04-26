# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Web Search service.

This module is the single orchestration point for fast web search.
It replaces the scattered search logic from legacy src/engine.py.

Architecture
------------
  1. Run DDGS search (optionally supplemented by hosted API engines)
  2. Deduplicate results by normalized URL, domain+title, snippet similarity
  3. Fetch previews for top candidates (httpx → curl_cffi, cache-first)
  4. Soft-rerank by semantic + lexical + trust signal
  5. Format and return a clean text response

All parameters default to values from core.config.SearchConfig.

Public API
----------
WebSearchService            -- async service class
run_web_search(query, ...)  -- top-level convenience coroutine
"""

from __future__ import annotations

import asyncio
import html as html_lib
import logging
import re
import secrets
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from core.models.search import SearchResult, SearchRichResult, SearchSource
from core.config import load_search_config
from core.fetch.ddgs_client import async_ddgs_search
from core.fetch.academic_fetcher import AcademicFetcher
from core.fetch.hosted_clients import async_hosted_search, available_hosted_engines
from core.query import (
    build_provider_query,
    filter_results_by_domain_constraints,
    parse_domain_constraints,
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
from core.fetch.url_utils import normalize_url
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

# Persistent HTTP connector — reused across preview-fetch batches to avoid
# rebuilding connection pools on every search call.
_http_connector: Optional["aiohttp.TCPConnector"] = None  # type: ignore[name-defined]


async def _get_http_connector(concurrency: int) -> "aiohttp.TCPConnector":  # type: ignore[name-defined]
    """Return (or lazily create) the shared TCPConnector for preview fetches."""
    global _http_connector
    import aiohttp as _aiohttp
    if _http_connector is None or _http_connector.closed:
        _http_connector = _aiohttp.TCPConnector(
            limit=concurrency * 4, limit_per_host=2, ttl_dns_cache=120
        )
    return _http_connector


async def shutdown_web_search() -> None:
    """Close shared HTTP connector on MCP server shutdown.

    Call this from the server lifespan handler to ensure open sockets are
    released cleanly instead of leaking on process exit.
    """
    global _http_connector
    if _http_connector is not None and not _http_connector.closed:
        await _http_connector.close()
        _http_connector = None


logger = logging.getLogger("services.web_search")
trace_logger = logging.getLogger("trace.web_search")

_DEFAULT_PREVIEW_FETCH_TIMEOUT = 6.0
_DEFAULT_PREVIEW_TOTAL_TIMEOUT = 12.0

_BOT_MIMIC_USER_AGENTS: tuple[str, ...] = (
    "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
    "TelegramBot (like TwitterBot)",
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
)
_BOT_MIMIC_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_BOT_MIMIC_OG_TITLE_RE = re.compile(
    r'<meta\s+(?:property|name)=["\']og:title["\']\s+content=["\'](.*?)["\']',
    re.IGNORECASE,
)
_BOT_MIMIC_OG_DESC_RE = re.compile(
    r'<meta\s+(?:property|name)=["\']og:description["\']\s+content=["\'](.*?)["\']',
    re.IGNORECASE,
)
_BOT_MIMIC_DESC_RE = re.compile(
    r'<meta\s+(?:property|name)=["\']description["\']\s+content=["\'](.*?)["\']',
    re.IGNORECASE,
)
_BOT_MIMIC_TAG_RE = re.compile(r"<[^>]+>")
_BOT_MIMIC_SPACE_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# URL utilities (inlined from legacy engine.py, no external deps)
# ---------------------------------------------------------------------------

def _make_request_id() -> str:
    return secrets.token_hex(4)

def _trace(req_id: str, stage: str, **fields: object) -> None:
    extras = " ".join(f"{key}={value!r}" for key, value in fields.items())
    message = f"req={req_id} stage={stage}"
    if extras:
        message = f"{message} {extras}"
    trace_logger.info(message)


# ---------------------------------------------------------------------------
# Query classification helpers
# ---------------------------------------------------------------------------

# _QUERY_STOPWORDS imported from core.cache.query_normalizer above

# ---------------------------------------------------------------------------
# Time range helpers
# ---------------------------------------------------------------------------

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


def _normalize_time_range(time_range: Optional[str]) -> Optional[str]:
    """Map a human-readable time range alias to a DDGS timelimit value.

    Returns None for unrecognised/empty input so the caller can decide
    whether to fall back to no filter or raise.

    >>> _normalize_time_range("today")  # "d"
    >>> _normalize_time_range("week")   # "w"
    >>> _normalize_time_range("y")      # "y"
    >>> _normalize_time_range(None)     # None
    """
    if not time_range:
        return None
    return _TIME_RANGE_MAP.get(time_range.strip().lower().replace("-", "_"))


# ---------------------------------------------------------------------------
# Smart timelimit inference
# ---------------------------------------------------------------------------

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


def _auto_timelimit(query_types: list[str]) -> Optional[str]:
    """Infer the appropriate DDGS timelimit from the classified query types.

    Uses the primary type.  Falls back to None (no restriction) for unknown types.
    """
    primary = query_types[0] if query_types else "general"
    return _AUTO_TIMELIMIT.get(primary, None)


# Ordering for timelimit values — smaller index = tighter (more restrictive) window.
_TIMELIMIT_ORDER: dict[str, int] = {"d": 0, "w": 1, "m": 2, "y": 3}


def _stricter_timelimit(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Return the more restrictive (shorter window) of two timelimits.

    None means "no restriction" — the least restrictive option.
    """
    if a is None:
        return b
    if b is None:
        return a
    return a if _TIMELIMIT_ORDER.get(a, 99) <= _TIMELIMIT_ORDER.get(b, 99) else b


def _year_hint_timelimit(
    query: str,
    mode: str,
    current: Optional[str],
    prev: Optional[str],
    older: Optional[str],
) -> Optional[str]:
    """Extract a year from the query and return a corresponding timelimit.

    Only fires when:
      - mode is "timelimit"
      - the query contains freshness hints OR a comma-preceded trailing year

    The most recent year found is used.  Maps:
      year >= this year  → *current*  (default "m")
      year == last year  → *prev*     (default "y")
      year <  last year  → *older*    (default None)
    """
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


def _strip_trailing_year(query: str) -> str:
    """Remove year/year-range tokens that a model appended as time hints.

    Three cases, in priority order:

    1. Comma-preceded trailing year ("AI developments, 2023-2024")
       → always stripped; comma signals it is a metadata tag.

    2. Freshness hint present ("latest AI news 2026", "GPT-5.4 2026 benchmarks latest")
       → ALL standalone year tokens stripped, anywhere in the query.
       Rationale: timelimit is already set automatically from the query type, so the
       year is redundant noise that can confuse the search engine.

    3. No freshness hint ("SOTA LLM benchmarks 2024")
       → left intact; the year is a genuine temporal anchor.
    """
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

_JOURNALISTIC_HINTS = frozenset({
    # English
    "latest", "news", "today", "yesterday", "breaking", "headline", "current",
    "update", "updates", "right now", "now",
    # Russian / Ukrainian
    "новости", "последние", "срочно", "сейчас", "сегодня", "прямо сейчас",
    "новини", "зараз", "сьогодні", "останні", "терміново",
    # German / Dutch
    "nachrichten", "aktuell", "heute", "neueste", "meldung",
    "nieuws", "vandaag", "laatste", "nu",
    # French
    "actualité", "aujourd'hui", "nouvelles", "dernières",
    # Spanish / Portuguese
    "noticias", "hoy", "últimas", "ahora",
    "notícias", "hoje", "agora",
    # Italian
    "notizie", "oggi", "ultime", "adesso",
    # Polish
    "wiadomości", "dziś", "dzisiaj", "ostatnie", "pilne",
    # Turkish
    "haberler", "bugün", "son dakika", "şimdi",
    # Arabic / Hebrew / Persian
    "أخبار", "اليوم", "عاجل", "آخر",
    "חדשות", "היום", "עכשיו", "אחרון",
    "اخبار", "امروز", "الان", "آخرین",
    # Japanese / Chinese / Korean
    "ニュース", "速報", "今日",
    "新闻", "今天", "快讯",
    "뉴스", "오늘", "속보",
    # Hindi / Greek / Thai
    "समाचार", "आज", "अभी", "ताज़ा",
    "νέα", "σήμερα", "τώρα", "τελευταία",
    "ข่าว", "วันนี้", "ล่าสุด", "ด่วน",
})

_TECHNICAL_HINTS = frozenset({
    # Languages / runtimes (language-agnostic proper nouns)
    "python", "javascript", "typescript", "java", "golang", "rust", "cpp",
    "c++", "ruby", "php", "swift", "kotlin", "scala", "bash", "shell",
    # Infra / tooling (proper nouns)
    "docker", "kubernetes", "k8s", "linux", "ubuntu", "git", "github",
    "gitlab", "sql", "postgresql", "mysql", "mongodb", "redis",
    "pytorch", "torch", "tensorflow", "jax", "numpy", "pandas", "scipy",
    # Universal technical acronyms
    "api", "sdk", "cli", "gui", "ide",
    # English — concepts
    "library", "package", "module", "framework", "function", "method",
    "class", "syntax", "interface", "type",
    # English — actions / doc keywords
    "install", "configure", "setup", "deploy", "build", "compile",
    "tutorial", "docs", "documentation", "reference", "guide", "howto",
    "example", "snippet", "changelog", "readme",
    # Russian / Ukrainian
    "установка", "настройка", "конфигурация", "документация",
    "руководство", "пример", "библиотека",
    "встановлення", "налаштування", "документація", "бібліотека",
    # German / Dutch
    "installieren", "konfigurieren", "dokumentation", "anleitung", "beispiel",
    "bibliothek", "entwicklung", "einrichten", "kompilieren",
    "installeren", "configureren", "handleiding", "voorbeeld",
    # French
    "installer", "configurer", "tutoriel", "exemple", "bibliothèque", "développement",
    # Spanish / Portuguese / Italian
    "instalar", "configurar", "documentación", "guía", "ejemplo", "biblioteca",
    "instalação", "documentação", "tutorial",
    "installare", "configurare", "documentazione", "guida", "libreria",
    # Polish / Turkish
    "instalacja", "konfiguracja", "dokumentacja", "poradnik", "przykład",
    "kurulum", "yapılandırma", "belge", "rehber", "kütüphane",
    # Arabic / Hebrew / Persian
    "تثبيت", "إعداد", "توثيق", "مكتبة",
    "התקנה", "תיעוד", "מדריך", "ספרייה",
    "نصب", "پیکربندی", "مستندات", "کتابخانه",
    # Chinese / Japanese / Korean
    "安装", "配置", "文档", "教程", "示例", "开发", "框架",
    "インストール", "設定", "ドキュメント", "チュートリアル", "ライブラリ",
    "설치", "설정", "문서", "튜토리얼", "라이브러리",
    # Hindi / Greek / Thai
    "स्थापना", "दस्तावेज़", "उदाहरण",
    "εγκατάσταση", "τεκμηρίωση", "παράδειγμα",
    "ติดตั้ง", "เอกสาร", "คู่มือ",
})

_TROUBLESHOOTING_HINTS = frozenset({
    # English
    "fix", "fixing", "fixed", "broken", "not working", "doesn't work",
    "won't", "can't", "cannot", "failed", "failure", "crash", "crashes",
    "issue", "bug", "bugs", "solve", "solution", "debug", "debugging",
    "troubleshoot", "workaround", "patch",
    # Russian / Ukrainian
    "не работает", "сломан", "проблема", "исправить", "решение",
    "не працює", "зламаний", "виправити", "рішення",
    # German / Dutch
    "fehler", "funktioniert nicht", "problem", "lösung", "beheben", "absturz",
    "fout", "werkt niet", "oplossing", "repareren",
    # French
    "erreur", "ne fonctionne pas", "problème", "solution", "corriger", "débogage",
    # Spanish / Portuguese / Italian
    "error", "no funciona", "problema", "solución", "arreglar", "depurar",
    "não funciona", "solução", "corrigir",
    "non funziona", "problema", "soluzione", "correggere",
    # Polish / Turkish
    "błąd", "nie działa", "rozwiązanie", "naprawić",
    "hata", "çalışmıyor", "sorun", "çözüm", "düzeltme",
    # Arabic / Hebrew / Persian
    "خطأ", "لا يعمل", "مشكلة", "حل", "إصلاح",
    "שגיאה", "לא עובד", "בעיה", "פתרון",
    "خطا", "کار نمی‌کند", "مشکل", "راه‌حل",
    # Chinese / Japanese / Korean
    "错误", "不工作", "故障", "问题", "修复", "调试",
    "エラー", "動かない", "バグ", "修正", "デバッグ",
    "오류", "작동 안 함", "버그", "수정", "디버그",
    # Hindi / Greek / Thai
    "त्रुटि", "काम नहीं", "समस्या", "समाधान",
    "σφάλμα", "δεν λειτουργεί", "πρόβλημα", "λύση",
    "ข้อผิดพลาด", "ไม่ทำงาน", "ปัญหา", "แก้ไข",
})

_ACADEMIC_HINTS = frozenset({
    # English
    "research", "study", "studies", "paper", "papers", "journal",
    "citation", "abstract", "hypothesis", "methodology", "dataset",
    "arxiv", "pubmed", "doi", "proceedings", "conference",
    "dissertation", "thesis", "peer-reviewed", "meta-analysis",
    # Russian / Ukrainian
    "исследование", "статья", "диссертация", "научный", "публикация",
    "дослідження", "наукова", "дисертація",
    # German / Dutch
    "forschung", "studie", "artikel", "zeitschrift", "dissertation", "wissenschaft",
    "onderzoek", "tijdschrift", "scriptie", "wetenschappelijk",
    # French
    "recherche", "étude", "revue", "thèse", "scientifique", "publication",
    # Spanish / Portuguese / Italian
    "investigación", "revista", "tesis", "científico",
    "pesquisa", "dissertação",
    "ricerca", "rivista", "scientifico",
    # Polish / Turkish
    "badania", "czasopismo", "naukowy",
    "araştırma", "makale", "dergi", "bilimsel",
    # Arabic / Hebrew / Persian
    "بحث", "دراسة", "مجلة", "أطروحة", "علمي",
    "מחקר", "מאמר", "עיתון", "עיוני",
    "پژوهش", "مطالعه", "مقاله", "رساله", "علمی",
    # Chinese / Japanese / Korean
    "研究", "论文", "期刊", "学术", "发表", "科学",
    "論文", "学術", "ジャーナル", "科学",
    "연구", "논문", "학술", "저널", "과학",
    # Hindi / Greek / Thai
    "शोध", "अध्ययन", "लेख", "वैज्ञानिक",
    "έρευνα", "μελέτη", "άρθρο", "επιστημονικός",
    "การวิจัย", "การศึกษา", "บทความ", "วิทยานิพนธ์",
})

_FORUM_HINTS = frozenset({
    # English
    "reddit", "stackoverflow", "forum", "discussion", "community",
    "opinion", "opinions", "thoughts", "experience", "experiences",
    "recommend", "recommendation", "advice", "suggest",
    "vs", "versus", "comparison", "compare", "anyone", "someone",
    # Russian / Ukrainian
    "форум", "обсуждение", "мнение", "советую", "рекомендую", "сравнение",
    "обговорення", "думка", "порада", "порівняння",
    # German / Dutch
    "forum", "diskussion", "meinung", "erfahrung", "empfehlung", "vergleich",
    "discussie", "mening", "ervaring", "aanbeveling", "vergelijking",
    # French
    "discussion", "opinion", "avis", "expérience", "recommandation", "comparaison",
    # Spanish / Portuguese / Italian
    "foro", "discusión", "opinión", "experiencia", "recomendación", "comparación",
    "fórum", "opinião", "experiência", "comparação",
    "discussione", "opinione", "esperienza", "confronto",
    # Polish / Turkish
    "dyskusja", "opinia", "doświadczenie", "rekomendacja", "porównanie",
    "tartışma", "görüş", "deneyim", "öneri", "karşılaştırma",
    # Arabic / Hebrew / Persian
    "منتدى", "نقاش", "رأي", "تجربة", "مقارنة",
    "פורום", "דיון", "דעה", "המלצה", "השוואה",
    "انجمن", "بحث", "نظر", "تجربه", "مقایسه",
    # Chinese / Japanese / Korean
    "论坛", "讨论", "意见", "经验", "推荐", "比较",
    "フォーラム", "意見", "経験", "おすすめ", "比較",
    "포럼", "토론", "의견", "경험", "추천", "비교",
    # Hindi / Greek / Thai
    "मंच", "चर्चा", "राय", "अनुभव", "सिफारिश", "तुलना",
    "φόρουμ", "συζήτηση", "γνώμη", "εμπειρία", "σύγκριση",
    "ฟอรั่ม", "การสนทนา", "ความคิดเห็น", "ประสบการณ์", "เปรียบเทียบ",
})

_SHOPPING_HINTS = frozenset({
    # English
    "buy", "purchase", "order", "price", "prices", "cheap", "cheapest",
    "affordable", "deal", "deals", "discount", "coupon", "sale",
    "amazon", "ebay", "shop", "store", "shipping", "delivery",
    # Russian / Ukrainian
    "купить", "цена", "стоимость", "заказать", "магазин", "скидка",
    "купити", "ціна", "вартість", "замовити", "знижка",
    # German / Dutch
    "kaufen", "preis", "günstig", "billig", "angebot", "rabatt", "bestellen",
    "kopen", "goedkoop", "aanbieding", "korting", "bestelling", "levering",
    # French
    "acheter", "prix", "pas cher", "offre", "réduction", "commander", "livraison",
    # Spanish / Portuguese / Italian
    "comprar", "precio", "barato", "oferta", "descuento", "tienda", "envío",
    "preço", "entrega",
    "comprare", "prezzo", "economico", "sconto", "negozio", "consegna",
    # Polish / Turkish
    "kupić", "cena", "tanie", "oferta", "rabat", "sklep", "zamówienie", "dostawa",
    "satın al", "fiyat", "ucuz", "teklif", "indirim", "sipariş", "teslimat",
    # Arabic / Hebrew / Persian
    "شراء", "سعر", "رخيص", "عرض", "خصم", "متجر", "توصيل",
    "לקנות", "מחיר", "זול", "הנחה", "חנות", "משלוח",
    "خرید", "قیمت", "ارزان", "تخفیف", "فروشگاه", "تحویل",
    # Chinese / Japanese / Korean
    "购买", "价格", "便宜", "折扣", "商店", "配送",
    "購入", "価格", "安い", "割引", "注文", "送料",
    "구매", "가격", "저렴", "할인", "주문", "배송",
    # Hindi / Greek / Thai
    "खरीदना", "कीमत", "सस्ता", "छूट", "डिलीवरी",
    "αγορά", "τιμή", "φθηνό", "έκπτωση", "παράδοση",
    "ซื้อ", "ราคา", "ถูก", "ส่วนลด", "จัดส่ง",
})

_FINANCE_HINTS = frozenset({
    # English
    "stock", "stocks", "market", "markets", "crypto", "bitcoin", "ethereum",
    "btc", "eth", "trading", "invest", "investment", "portfolio",
    "nasdaq", "nyse", "s&p", "sp500", "dow", "forex", "currency",
    "bond", "etf", "dividend", "earnings", "ipo",
    # Russian / Ukrainian
    "акции", "биржа", "курс", "рубль", "доллар", "инвестиции",
    "акції", "ринок", "крипто", "інвестиції", "валюта",
    # German / Dutch
    "aktie", "aktien", "markt", "krypto", "investition", "börse", "währung",
    "aandeel", "markt", "crypto", "investering", "beurs", "valuta",
    # French
    "action", "actions", "marché", "crypto", "investissement", "bourse", "devise",
    # Spanish / Portuguese / Italian
    "acción", "acciones", "mercado", "inversión", "bolsa", "divisa",
    "ação", "ações", "investimento",
    "azione", "azioni", "mercato", "investimento", "borsa",
    # Polish / Turkish
    "akcja", "rynek", "krypto", "inwestycja", "giełda", "waluta",
    "hisse", "piyasa", "kripto", "yatırım", "borsa",
    # Arabic / Hebrew / Persian
    "أسهم", "سوق", "استثمار", "بورصة", "عملة",
    "מניות", "שוק", "השקעה", "בורסה", "מטבע",
    "سهام", "بازار", "سرمایه‌گذاری", "بورس",
    # Chinese / Japanese / Korean
    "股票", "市场", "加密货币", "投资", "交易所", "货币",
    "株式", "仮想通貨", "投資", "取引所", "通貨",
    "주식", "시장", "암호화폐", "투자", "거래소",
    # Hindi / Greek / Thai
    "शेयर", "बाजार", "निवेश", "क्रिप्टो",
    "μετοχές", "αγορά", "επένδυση", "κρυπτό",
    "หุ้น", "ตลาด", "ลงทุน", "คริปโต",
})

_MEDICAL_HINTS = frozenset({
    # English
    "symptom", "symptoms", "disease", "condition", "treatment",
    "medicine", "medication", "drug", "dose", "dosage",
    "diagnosis", "therapy", "syndrome", "cancer", "diabetes",
    "infection", "vaccine", "surgery", "doctor", "physician", "health",
    "medical", "clinical", "clinical trial", "clinical trials", "biotechnology",
    "biotech", "crispr", "gene therapy", "gene editing", "implant", "implants",
    "neuralink", "brain-computer", "brain computer",
    # Russian / Ukrainian
    "симптом", "болезнь", "лечение", "препарат", "диагноз", "здоровье",
    "симптом", "хвороба", "лікування", "препарат", "діагноз",
    "медицинские", "медицина", "рак", "вакцины", "вакцина",
    "генная терапия", "биотехнологии", "биотехнология", "редактирование генов",
    "клинические испытания", "нейроинтерфейс", "нейроинтерфейсы",
    "имплантат", "имплантаты", "мозг-компьютер", "мозг компьютер",
    # German / Dutch
    "symptom", "krankheit", "behandlung", "medikament", "diagnose", "therapie", "arzt",
    "ziekte", "behandeling", "medicijn", "gezondheid", "dokter",
    # French
    "symptôme", "maladie", "traitement", "médicament", "diagnostic", "santé", "médecin",
    # Spanish / Portuguese / Italian
    "síntoma", "enfermedad", "tratamiento", "medicamento", "diagnóstico", "salud", "médico",
    "sintoma", "doença", "tratamento", "saúde",
    "sintomo", "malattia", "trattamento", "farmaco", "diagnosi", "salute",
    # Polish / Turkish
    "objaw", "choroba", "leczenie", "lek", "diagnoza", "zdrowie", "lekarz",
    "belirti", "hastalık", "tedavi", "ilaç", "teşhis", "sağlık",
    # Arabic / Hebrew / Persian
    "مرض", "علاج", "دواء", "تشخيص", "صحة", "طبيب",
    "מחלה", "טיפול", "תרופה", "אבחנה", "בריאות", "רופא",
    "بیماری", "درمان", "دارو", "تشخیص", "سلامت",
    # Chinese / Japanese / Korean
    "症状", "疾病", "治疗", "药物", "诊断", "健康", "医生",
    "症状", "病気", "治療", "薬", "診断", "健康", "医師",
    "증상", "질병", "치료", "약물", "진단", "건강",
    # Hindi / Greek / Thai
    "लक्षण", "बीमारी", "उपचार", "स्वास्थ्य",
    "σύμπτωμα", "ασθένεια", "θεραπεία", "υγεία",
    "อาการ", "โรค", "การรักษา", "ยา", "สุขภาพ",
})

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


def infer_query_language(query: str) -> str:
    """Detect the dominant script of a query using Unicode block counts.

    Returns a 2-letter language code understood by DDGS region mapping,
    or "en" as the default fallback for Latin/undetected scripts.

    Detection is purely character-based (no external deps):
      - Script-specific Unicode blocks give unambiguous signals for
        Cyrillic, Arabic, Hebrew, CJK, Kana, Hangul, Thai, Devanagari, Greek.
      - Latin-based languages (de, fr, es, …) are NOT distinguished here;
        they route through the English engine-router path, which handles
        them fine via the wt-wt region.
    """
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


_ORDERED_QUERY_TYPES: list[tuple[str, frozenset]] = [
    ("finance",         _FINANCE_HINTS),
    ("medical",         _MEDICAL_HINTS),
    ("journalistic",    _JOURNALISTIC_HINTS),
    ("academic",        _ACADEMIC_HINTS),
    ("shopping",        _SHOPPING_HINTS),
    ("troubleshooting", _TROUBLESHOOTING_HINTS),
    ("forum",           _FORUM_HINTS),
    ("technical",       _TECHNICAL_HINTS),
]


def infer_query_types(query: str) -> list[str]:
    """Classify query into all matching routing-aware types (up to 3).

    Returns types in priority order — the first entry is the primary type.
    Having multiple types enables combinatorial backend/TTL selection:
    "activated charcoal price" → ["shopping", "medical"] routes through
    both backends and uses the shorter (shopping) TTL.

    Priority order (most specific → least):
        finance > medical > journalistic > academic > shopping
        > troubleshooting > forum > technical > general
    """
    q = str(query or "").lower()
    tokens = set(q.split())

    def _matches(hints: frozenset) -> bool:
        return bool(tokens & hints) or any(h in q for h in hints if " " in h)

    matched = [qt for qt, hints in _ORDERED_QUERY_TYPES if _matches(hints)]
    return matched[:3] if matched else ["general"]


def _parse_query_profile(query: str) -> dict:
    q = (query or "").lower()
    years = _YEAR_RE.findall(query)
    tokens = set(q.split())
    has_intent = bool(tokens & _JOURNALISTIC_HINTS)
    return {"years": years, "has_intent": has_intent, "terms": _query_terms(query)}


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

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
    """Decision produced by _triage_results for one search result."""
    skip: bool          # True → don't fetch, use snippet only
    fetch_policy: str   # "cheap" (httpx only) | "race" (httpx + curl_cffi parallel)
    score: float        # triage relevance score [0, 1]


def _triage_soft_score(
    result: SearchResult,
    query: str,
    *,
    index: int,
    total: int,
) -> float:
    """Cheap lexical/trust score used before preview fetching."""
    title = (result.title or "").strip()
    snippet = (result.snippet or "").strip()
    pos_score = 1.0 - (index / max(total - 1, 1))
    snip_score = min(1.0, len(snippet) / 300)
    lex = _lexical_score(query, title, snippet, result.url)
    tier_trust = _TIER_TRUST_SCORES.get(result.trust_tier or "unknown", 0.5)
    date_boost = 0.08 if _DATE_SIGNAL_RE.search(snippet) else 0.0
    hub_pen = _hub_penalty(result.url, title, snippet)

    score = (
        0.25 * pos_score
        + 0.10 * snip_score
        + 0.40 * lex
        + 0.15 * tier_trust
        + date_boost
        - 0.20 * hub_pen
    )
    return max(0.0, min(1.0, score))


def _triage_one_result(
    result: SearchResult,
    query: str,
    *,
    index: int,
    total: int,
    trust_reg=None,
    rep_store=None,
) -> TriageResult:
    """Run the cheap triage logic for a single result."""
    url = result.url
    title = (result.title or "").strip()
    snippet = (result.snippet or "").strip()
    title_lower = title.lower()

    if result.trust_tier == "?" and trust_reg is not None:
        tier = trust_reg.get_tier(url)
        if tier:
            result.trust_tier = tier

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


def _triage_results(results: list[SearchResult], query: str) -> list[TriageResult]:
    """Cheap per-result triage (< 1ms each, no network).

    Returns a TriageResult per result:
      - skip: whether to skip preview fetch entirely
      - fetch_policy: "cheap" or "race" (determines parallelism in fetch)
      - score: relevance signal

    Side effect: populates result.trust_tier when it's still "?".
    """
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


def _dedup_results(results: list[SearchResult]) -> list[SearchResult]:
    """Dedup by normalized URL, domain+title, and snippet signature."""
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
        snip_key = " ".join((r.snippet or "").lower().split()[:20])
        if title_key in seen_keys or (snip_key and snip_key in seen_keys):
            continue
        seen_keys.add(title_key)
        if snip_key:
            seen_keys.add(snip_key)
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

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


def _trust_blend_weights(query_type: str) -> tuple[float, float]:
    return _TRUST_BLEND_WEIGHTS.get(query_type, _TRUST_BLEND_WEIGHTS["general"])


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




def _year_match_score(text: str, years: list[str]) -> float:
    if not years or not text:
        return 0.0
    text_l = text.lower()
    found_years = set(_YEAR_RE.findall(text_l))
    if not found_years:
        return 0.0
    hits = set(years) & found_years
    return 1.0 if hits else -0.3


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

    score = (
        0.20 * original_rank
        + 0.20 * lex
        + 0.35 * max(0.0, min(payload.semantic_score, 1.0))
        + 0.12 * trust
        + 0.08 * max(0.0, min(payload.quality_score, 1.0))
    )
    if profile["years"]:
        score += 0.20 * year_score
    score -= 0.30 * hub_pen
    score += _academic_engine_bonus(result, query_type)
    return max(0.0, score)


def _content_quality_signal(payload: PreviewPayload, result: SearchResult, query: str) -> float:
    """Raw content quality signal for reputation recording.

    Deliberately excludes position/trust/rank so that the reputation system
    tracks actual content quality, not search-engine ranking or existing tier.
    Only called when payload.text is non-empty (fetch succeeded).
    """
    lex = _lexical_score(query, result.title or "", result.snippet or "", result.url)
    return (
        0.45 * max(0.0, min(float(payload.semantic_score or 0.0), 1.0))
        + 0.35 * max(0.0, min(float(payload.quality_score or 0.0), 1.0))
        + 0.20 * lex
    )


def _bot_mimic_applies(query_types: list[str], cfg) -> bool:
    mode = str(getattr(cfg.search, "bot_mimic_mode", "off") or "off").strip().lower()
    if mode not in {"fallback", "always"}:
        return False
    allowed = list(getattr(cfg.search, "bot_mimic_for_query_types", []) or [])
    return not allowed or any(qt in allowed for qt in query_types)


def _bot_mimic_candidate_indices(
    results: list[SearchResult],
    triage: list[TriageResult],
    *,
    mode: str,
    top_k: int,
) -> list[int]:
    if top_k <= 0:
        return []

    registry = get_registry()
    selected: list[int] = []
    for idx, (result, tr) in enumerate(zip(results, triage)):
        if tr.skip:
            continue
        if mode == "fallback":
            try:
                if not registry.lookup(result.url).try_preview_bot:
                    continue
            except Exception as exc:
                logger.debug("domain registry lookup failed for %s: %s", result.url, exc)
                continue
        selected.append(idx)
        if len(selected) >= top_k:
            break
    return selected


def _bot_mimic_extract_fields(url: str, raw_html: str) -> tuple[str, str]:
    title_match = _BOT_MIMIC_TITLE_RE.search(raw_html or "")
    og_title_match = _BOT_MIMIC_OG_TITLE_RE.search(raw_html or "")
    og_desc_match = _BOT_MIMIC_OG_DESC_RE.search(raw_html or "")
    desc_match = _BOT_MIMIC_DESC_RE.search(raw_html or "")

    title = html_lib.unescape((og_title_match or title_match).group(1)).strip() if (og_title_match or title_match) else ""
    snippet = ""
    for match in (og_desc_match, desc_match):
        if match:
            snippet = html_lib.unescape(match.group(1)).strip()
            break

    if not snippet:
        try:
            markdown = normalize_page(url, raw_html)
        except Exception:
            markdown = _BOT_MIMIC_TAG_RE.sub(" ", raw_html or "")
        snippet = _BOT_MIMIC_SPACE_RE.sub(" ", markdown or "").strip(" -|")

    return title[:200].strip(), snippet[:800].strip()


async def _bot_mimic_fetch_one(
    session,
    url: str,
    *,
    timeout: float,
) -> tuple[str, str] | None:
    headers_base = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    for user_agent in _BOT_MIMIC_USER_AGENTS:
        headers = dict(headers_base)
        headers["User-Agent"] = user_agent
        try:
            async with session.get(url, allow_redirects=True, headers=headers) as resp:
                if resp.status >= 400:
                    continue
                content_type = (resp.headers.get("Content-Type") or "").lower()
                if content_type and all(token not in content_type for token in ("html", "xml", "text")):
                    continue
                raw_html = await asyncio.wait_for(resp.text(errors="replace"), timeout=timeout)
        except Exception:
            continue

        if not raw_html or is_antibot(raw_html):
            continue

        title, snippet = _bot_mimic_extract_fields(url, raw_html)
        if title or snippet:
            return title, snippet
    return None


async def _bot_mimic_enrich_results(
    results: list[SearchResult],
    triage: list[TriageResult],
    *,
    query_types: list[str],
    cfg,
    deadline: float | None = None,
) -> dict[int, tuple[str, str]]:
    if not _bot_mimic_applies(query_types, cfg):
        return {}

    mode = str(getattr(cfg.search, "bot_mimic_mode", "off") or "off").strip().lower()
    top_k = int(getattr(cfg.search, "bot_mimic_top_k", 0) or 0)
    timeout = float(getattr(cfg.search, "bot_mimic_timeout_seconds", 0.8) or 0.8)
    indices = _bot_mimic_candidate_indices(results, triage, mode=mode, top_k=top_k)
    if not indices:
        return {}

    if deadline is not None:
        remaining = max(0.0, deadline - asyncio.get_running_loop().time() - 0.2)
        if remaining < 0.2:
            return {}
        timeout = min(timeout, remaining)

    import aiohttp

    connector = await _get_http_connector(max(1, min(len(indices), 4)))
    client_timeout = aiohttp.ClientTimeout(total=max(0.2, timeout))
    async with aiohttp.ClientSession(timeout=client_timeout, connector=connector, connector_owner=False) as session:
        tasks = [asyncio.create_task(_bot_mimic_fetch_one(session, results[idx].url, timeout=timeout)) for idx in indices]
        fetched = await asyncio.gather(*tasks, return_exceptions=True)

    enriched: dict[int, tuple[str, str]] = {}
    for idx, payload in zip(indices, fetched):
        if isinstance(payload, Exception) or not payload:
            continue
        title, snippet = payload
        if title or snippet:
            enriched[idx] = (title, snippet)
    return enriched


# ---------------------------------------------------------------------------
# Preview fetching
# ---------------------------------------------------------------------------

from core.fetch.constants import DEFAULT_UA as _UA
_PREFETCH_MAX_URLS: int = 5   # cap on background prefetch targets per search
_PREFETCH_FETCH_TIMEOUT: float = 8.0
# Limit concurrent background prefetch tasks to avoid socket exhaustion under burst load.
_PREFETCH_SEMAPHORE: Optional[asyncio.Semaphore] = None


def _get_prefetch_semaphore() -> asyncio.Semaphore:
    global _PREFETCH_SEMAPHORE
    if _PREFETCH_SEMAPHORE is None:
        _PREFETCH_SEMAPHORE = asyncio.Semaphore(3)
    return _PREFETCH_SEMAPHORE


async def _prefetch_urls_background(urls: list[str], req_id: str = "-") -> None:
    """Background task: fetch uncached URLs into SourceCache.

    Fire-and-forget — called via ``asyncio.create_task()``.  Any exception is
    silently swallowed so it never surfaces in the main search response.

    Reuses the shared TCPConnector, so no new connection pools are created.
    Only HTML/text content-types are stored; antibot pages are skipped.
    URLs already fresh in cache are skipped immediately.
    """
    import aiohttp as _aiohttp

    to_fetch = [u for u in urls if not _cache.is_fresh(u)]
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
            timeout = _aiohttp.ClientTimeout(total=_PREFETCH_FETCH_TIMEOUT)
            async with _aiohttp.ClientSession(
                connector=connector, connector_owner=False,
                timeout=timeout, headers={"User-Agent": _UA},
            ) as session:
                for url in to_fetch:
                    try:
                        async with session.get(url, allow_redirects=True) as resp:
                            if resp.status >= 400:
                                continue
                            ct = (resp.headers.get("Content-Type") or "").lower()
                            if ct and all(m not in ct for m in ("html", "text")):
                                continue
                            raw_html = await resp.text(errors="replace")
                            if raw_html and not is_antibot(raw_html):
                                clean_text = normalize_page(url, raw_html, "")
                                if clean_text:
                                    _cache.cache_page(url, "", clean_text=clean_text)
                                    _trace(req_id, "prefetch.cached", url=url)
                    except Exception as _e:
                        logger.debug("prefetch fetch failed for %s: %s", url, _e)
        except Exception as _e:
            logger.debug("prefetch batch error: %s", _e)




async def _fetch_pdf_preview(
    url: str,
    query: str,
    loop,
    req_id: str = "-",
) -> PreviewPayload:
    """Download a PDF URL, extract text, densify with GliNER, return PreviewPayload.

    Uses a strict 5 MB download cap and a 3 K char output target —
    much tighter than read_page's full-extraction path.
    """
    _UA_PDF = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    def _fetch_bytes() -> bytes:
        # httpx streaming with size guard
        try:
            import httpx
            with httpx.Client(
                headers={"User-Agent": _UA_PDF, "Accept": "application/pdf,*/*;q=0.8"},
                timeout=20.0,
                follow_redirects=True,
                verify=True,
            ) as client:
                with client.stream("GET", url) as r:
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
        except Exception as _e:
            logger.debug("pdf httpx fetch failed for %s: %s", url, _e)
        # curl_cffi fallback
        try:
            from curl_cffi import requests as cffi_req
            r = cffi_req.get(
                url, impersonate="chrome124", timeout=20,
                headers={"User-Agent": _UA_PDF, "Accept": "application/pdf,*/*;q=0.8"},
            )
            data = bytes(r.content or b"")
            if 200 <= r.status_code < 400 and len(data) <= _PDF_PREVIEW_MAX_BYTES and looks_like_pdf_bytes(data):
                return data
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
            timeout=15.0,
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


async def _fetch_preview_one(
    session,
    result: SearchResult,
    query: str,
    settings: dict,
    sem: asyncio.Semaphore,
    loop,
    policy: str = "cheap",
    fetch_timeout: float = 8.0,
    req_id: str = "-",
) -> PreviewPayload:
    """Fetch one page preview.

    policy="cheap"  — aiohttp only (saves connections for lower-relevance results)
    policy="race"   — aiohttp + curl_cffi launched simultaneously; first
                      non-antibot response wins, loser is cancelled.
    """
    async with sem:
        url = result.url
        t0 = time.perf_counter()

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
                async with session.get(url, allow_redirects=True) as resp:
                    if resp.status >= 400:
                        return None
                    ct = (resp.headers.get("Content-Type") or "").lower()
                    if ct and all(m not in ct for m in ("html", "xml", "text")):
                        return None
                    text = await resp.text(errors="replace")
                    return text if text and not is_antibot(text) else None
            except Exception:
                return None

        async def _curl() -> str | None:
            def _sync() -> str | None:
                try:
                    from curl_cffi import requests as cffi_req
                    r = cffi_req.get(url, impersonate="chrome124", timeout=12, headers={"User-Agent": _UA})
                    text = r.text
                    return text if text and not is_antibot(text) else None
                except Exception:
                    return None
            return await loop.run_in_executor(_io_pool,_sync)

        # Fast path: if clean_text is already cached, skip fetch + parse entirely.
        cached_page = _cache.get_cached(url)
        if cached_page and _cache.is_fresh(url) and cached_page.clean_text:
            return PreviewPayload(text=cached_page.clean_text)

        raw_html: str | None = None
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

        try:
            payload = await asyncio.wait_for(
                loop.run_in_executor(
                    _io_pool,
                    lambda: build_preview_payload(url, raw_html, query=query, settings=settings),
                ),
                timeout=fetch_timeout,
            )
        except Exception as exc:
            logger.debug("preview payload build failed for %s: %s", url, exc)
            _trace(req_id, "preview_fetch.payload_error", url=url, policy=policy, elapsed=round(time.perf_counter() - t0, 3))
            return PreviewPayload()

        # Cache the processed text so future hits skip fetch + parse.
        if payload.text:
            _cache.cache_page(url, result.title or "", clean_text=payload.text)
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
    """Fetch previews for a list of results concurrently.

    policies — parallel list of fetch policies per result ("cheap" | "race").
               If None, defaults to "cheap" for all.
    early_return_threshold — cancel remaining fetches after this many non-empty
                             payloads are collected (0 = wait for all).
    """
    import aiohttp
    import math as _math

    if not results:
        return []

    if policies is None:
        policies = ["cheap"] * len(results)

    sem = asyncio.Semaphore(concurrency)
    timeout = aiohttp.ClientTimeout(total=fetch_timeout)
    connector = await _get_http_connector(concurrency)
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
            timeout=10.0,
        )
        _trace(req_id, "preview_batch.warm_done", elapsed=round(time.perf_counter() - warm_t0, 3))
    except Exception:
        _trace(req_id, "preview_batch.warm_failed", elapsed=round(time.perf_counter() - warm_t0, 3))
        pass

    try:
        async with aiohttp.ClientSession(
            timeout=timeout, connector=connector, connector_owner=False,
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
# Result formatting
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Per-query-type output profiles
# ---------------------------------------------------------------------------

@dataclass
class _OutputProfile:
    """Controls how many results are shown and how deeply they are parsed.

    Two strategies:
      depth-first  — fewer results, richer parsed content, optional bonus snippets
      breadth-first — more results, shallow parsing, speed over depth
    """
    max_results: int           # final result count shown to the model
    preview_fetch_limit: int   # max pages to actually scrape
    unparsed_bonus: int        # unparsed results appended if score ≥ threshold
    min_score_unparsed: float  # final-score floor for unparsed bonus results


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


def _get_output_profile(query_types: list[str]) -> _OutputProfile:
    """Return the output profile for the primary query type."""
    return _OUTPUT_PROFILES.get(query_types[0] if query_types else "general",
                                _DEFAULT_OUTPUT_PROFILE)


def _effective_output_limit(profile: _OutputProfile, opts: WebSearchOptions) -> int:
    """Return the final model-visible result cap for this query."""
    return max(1, min(int(profile.max_results), int(opts.max_results)))


def _adapt_output_profile(
    results: list[SearchResult],
    triage: list[TriageResult],
    base_profile: _OutputProfile,
    *,
    query_types: list[str],
    payloads: list[PreviewPayload] | None = None,
) -> tuple[_OutputProfile, dict[str, object]]:
    """Expand technical/troubleshooting output breadth when evidence is thin.

    This controller is intentionally conservative:
      - only widens output for technical-style queries
      - only expands, never shrinks, the baseline profile
      - post-fetch adaptation can widen the displayed set, but does not refetch
    """
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
    profile.max_results = min(max(profile.max_results, base_profile.max_results) + growth, 10)
    if payloads is None:
        profile.preview_fetch_limit = min(
            max(profile.preview_fetch_limit, base_profile.preview_fetch_limit) + 1,
            7,
        )
    profile.unparsed_bonus = min(max(profile.unparsed_bonus, base_profile.unparsed_bonus) + 1, 3)
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


def _enrich_pdf_urls(results: list[SearchResult]) -> list[SearchResult]:
    for result in results:
        result.pdf_url = _infer_pdf_url(result)
    return results


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


def _display_text(text: str, limit: int) -> str:
    compact = " ".join((text or "").split()).strip(" ,;:|-")
    if not compact:
        return ""
    return compact[:limit].rstrip(" ,;:|-")


def _source_domain(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host.removeprefix("www.")


def _display_domain(domain: str) -> str:
    parts = [p for p in (domain or "").split(".") if p]
    if len(parts) >= 2:
        label = parts[-2]
    elif parts:
        label = parts[0]
    else:
        return ""
    return label.replace("-", " ").title()


def _favicon_url(domain: str) -> str:
    return f"https://icons.duckduckgo.com/ip3/{domain}.ico" if domain else ""


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
    return SearchSource(
        id=source_id or f"source-{rank}",
        rank=rank,
        title=(result.title or "").strip(),
        url=(result.url or "").strip(),
        domain=domain,
        display_domain=_display_domain(domain) or domain,
        favicon_url=_favicon_url(domain),
        snippet=_display_text(result.snippet or "", snippet_limit),
        preview=_display_text(preview or result.snippet or "", preview_limit),
        published_date=_normalize_date(result.published_date) or (result.published_date or ""),
        engine=result.engine or "",
        trust_tier=result.trust_tier or "?",
        score=round(float(score if score is not None else result.score or 0.0), 4),
        pdf_url=_infer_pdf_url(result),
    )


def _build_model_context(query: str, sources: list[SearchSource]) -> str:
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
    for source in sources:
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
    return "\n".join(lines).strip()


def _citation_source_id(search_id: str, rank: int) -> str:
    compact = re.sub(r"[^a-z0-9]+", "", (search_id or "").lower())
    compact = compact.removeprefix("srch")
    namespace = (compact[:3] or "src").ljust(3, "0")
    return f"c{namespace}-{rank}"


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


def _normalize_date(raw: str) -> str:
    """Normalize any engine date string to 'Mon DD, YYYY'. Returns '' if unparseable."""
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
    """Build the final text output for the MCP tool.

    output_profile — controls result count and depth-first vs breadth-first
    selection. Depth-first types (technical, academic, …) prefer parsed
    results and add unparsed bonus only if score meets the threshold.
    Breadth-first types (journalistic, forum, …) just take top N by score.

    total_char_budget — if > 0, stop adding result blocks once the cumulative
    character count would exceed it (prevents flooding the model context).
    """
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

    scored.sort(key=lambda x: (-x[0], x[1]))

    # -- Result selection: depth-first vs breadth-first ----------------------
    #
    # depth-first (unparsed_bonus > 0):
    #   Take top (max_results − bonus) parsed results first, then append up to
    #   `bonus` unparsed results that still score above the threshold.
    #   This ensures the model sees rich content for technical/medical queries
    #   without being padded with low-quality stubs.
    #
    # breadth-first (unparsed_bonus == 0):
    #   Just take top max_results by score — volume beats depth for news/forum.
    #
    if output_profile.unparsed_bonus > 0:
        parsed   = [(s, i, r, p) for s, i, r, p in scored if p.text]
        unparsed = [(s, i, r, p) for s, i, r, p in scored if not p.text]
        parsed_take = max(0, max_results - output_profile.unparsed_bonus)
        selected = parsed[:parsed_take]
        for item in unparsed:
            if len(selected) - parsed_take >= output_profile.unparsed_bonus:
                break
            if item[0] >= output_profile.min_score_unparsed:
                selected.append(item)
        selected.sort(key=lambda x: (-x[0], x[1]))
        final = selected[:max_results]
    else:
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


# ---------------------------------------------------------------------------
# WebSearchService
# ---------------------------------------------------------------------------

@dataclass
class WebSearchOptions:
    max_results: int = 10
    fetch_previews: bool = True
    concurrency: int = 4
    fetch_timeout: float = 6.0
    total_timeout: float = 12.0
    timelimit: Optional[str] = None   # DDGS time filter: "d", "w", "m", "y"


class WebSearchService:
    """Orchestrate fast web search across DDGS and hosted search APIs."""

    def __init__(self, options: Optional[WebSearchOptions] = None) -> None:
        cfg = load_search_config()
        self._cfg = cfg
        self._opts = options or WebSearchOptions(
            max_results=cfg.search.max_results,
            fetch_timeout=cfg.search.preview_fetch_timeout,
            total_timeout=cfg.search.preview_total_timeout,
        )

    async def _run_search_pipeline(
        self,
        query: str,
        lang: str,
        query_types: list[str],
        query_type: str,
        out_profile: _OutputProfile,
        opts: WebSearchOptions,
        req_id: str = "-",
    ) -> tuple[list[SearchResult], list]:
        """Shared provider fetch → merge → dedup → triage. Returns (deduped, triage)."""
        pool_multiplier = max(1, int(self._cfg.search.candidate_pool_multiplier))
        buffer = max(0, int(self._cfg.search.result_buffer_size))
        fetch_max = out_profile.max_results + buffer

        hosted_engines = available_hosted_engines()
        use_fast_academic = bool({"academic", "medical"} & set(query_types))
        n_hosted = len(hosted_engines)
        ddgs_multiplier = max(1, pool_multiplier - n_hosted)
        ddgs_hedge = max(1, 2 - n_hosted)
        hosted_max = fetch_max
        academic_max = min(fetch_max, 8)

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
        deduped = _dedup_results(merged)
        _trace(req_id, "merge.done",
               elapsed=round(time.perf_counter() - merge_t0, 3),
               merged=len(merged), deduped=len(deduped))

        triage = _triage_results(deduped, query) if deduped else []
        return deduped, triage

    async def search(self, query: str, deadline: float | None = None) -> str:
        """Run web search and return formatted text result."""
        opts = self._opts
        req_id = _make_request_id()
        overall_t0 = time.perf_counter()
        original_query = query
        pool_multiplier = max(1, int(self._cfg.search.candidate_pool_multiplier))
        preview_fetch_limit = max(1, int(self._cfg.search.preview_fetch_limit))
        snippet_char_budget = max(600, int(self._cfg.search.max_snippet_chars))
        preview_char_budget = max(
            int(self._cfg.search.preview_max_chars),
            int(self._cfg.search.max_snippet_chars),
        )
        constraints = parse_domain_constraints(query)
        analysis_query = constraints.clean_query or query
        analysis_query, _ = _apply_year_hint_policy(analysis_query, self._cfg.query)
        provider_query = build_provider_query(original_query, constraints) or analysis_query
        query = analysis_query
        lang = infer_query_language(query)
        query_types = infer_query_types(query)
        query_type = query_types[0]
        query_profile = _parse_query_profile(query)
        out_profile = _get_output_profile(query_types)

        # Per-type profile overrides config defaults for fetch depth and output count.
        # preview_fetch_limit: how many pages to scrape (depth-first types scrape more)
        # max_results: passed to _format_results — breadth-first types show more results
        preview_fetch_limit = out_profile.preview_fetch_limit

        logger.info(
            "web_search query=%r lang=%s types=%s profile=max%d/fetch%d/bonus%d",
            query, lang, query_types,
            out_profile.max_results, out_profile.preview_fetch_limit, out_profile.unparsed_bonus,
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
            include_domains=constraints.include_domains,
            exclude_domains=constraints.exclude_domains,
            out_max_results=out_profile.max_results,
            out_preview_fetch_limit=out_profile.preview_fetch_limit,
            out_unparsed_bonus=out_profile.unparsed_bonus,
            fetch_previews=opts.fetch_previews,
            chosen_profile=f"{out_profile.max_results}/{out_profile.preview_fetch_limit}/{out_profile.unparsed_bonus}",
        )

        deduped, triage = await self._run_search_pipeline(
            provider_query, lang, query_types, query_type, out_profile, opts, req_id
        )
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
            out_profile = adapted_profile
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
            preview_settings = get_preview_settings(apply_hardware_profile=False)
            fetched = await _fetch_previews(
                to_fetch,
                query=query,
                concurrency=opts.concurrency,
                fetch_timeout=opts.fetch_timeout,
                total_timeout=opts.total_timeout,
                preview_settings=preview_settings,
                loop=loop,
                policies=to_fetch_policies,
                early_return_threshold=max(0, int(self._cfg.search.early_return_threshold)),
                req_id=req_id,
                deadline=deadline,
            )
            for i, payload in zip(to_fetch_indices, fetched):
                payloads[i] = payload

        adapted_post_profile, post_meta = _adapt_output_profile(
            deduped,
            triage,
            out_profile,
            query_types=query_types,
            payloads=payloads,
        )
        if adapted_post_profile != out_profile:
            out_profile = adapted_post_profile
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

        enriched_regular = await _bot_mimic_enrich_results(
            deduped,
            triage,
            query_types=query_types,
            cfg=self._cfg,
            deadline=deadline,
        )
        if enriched_regular:
            _trace(
                req_id,
                "bot_mimic.regular",
                trigger_reason="regular_rank_enrichment",
                chosen_top_k=len(enriched_regular),
                fallback_path="rank_only",
            )
            for idx, (title, snippet) in enriched_regular.items():
                enriched_result = replace(
                    deduped[idx],
                    title=title or deduped[idx].title,
                    snippet=snippet or deduped[idx].snippet,
                )
                enriched_tr = _triage_one_result(
                    enriched_result,
                    query,
                    index=0,
                    total=1,
                )
                triage[idx] = TriageResult(
                    skip=triage[idx].skip and enriched_tr.skip,
                    fetch_policy=enriched_tr.fetch_policy if enriched_tr.score > triage[idx].score else triage[idx].fetch_policy,
                    score=max(triage[idx].score, enriched_tr.score),
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
            total_char_budget=self._cfg.search.total_context_budget,
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

    async def search_structured(
        self,
        query: str,
        deadline: float | None = None,
    ) -> list[SearchResult]:
        """Run the safe search pipeline and return ranked SearchResult items.

        This is the deep-research entry point. It preserves the current isolated
        provider lifecycle and cheap triage scoring, but skips preview formatting.
        """
        opts = self._opts
        constraints = parse_domain_constraints(query)
        analysis_query = constraints.clean_query or query
        analysis_query, _ = _apply_year_hint_policy(analysis_query, self._cfg.query)
        provider_query = build_provider_query(query, constraints) or analysis_query
        query = analysis_query
        lang = infer_query_language(query)
        query_types = infer_query_types(query)
        query_type = query_types[0]
        out_profile = _get_output_profile(query_types)

        req_id = _make_request_id()
        deduped, triage = await self._run_search_pipeline(
            provider_query, lang, query_types, query_type, out_profile, opts, req_id
        )
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
            out_profile = adapted_profile
            _trace(
                req_id,
                "structured.profile.adapt",
                trigger_reason=";".join(list(adapt_meta.get("reasons", []))),
                chosen_profile=f"{out_profile.max_results}/{out_profile.preview_fetch_limit}/{out_profile.unparsed_bonus}",
                chosen_top_k=out_profile.max_results,
            )

        enriched = await _bot_mimic_enrich_results(
            deduped,
            triage,
            query_types=query_types,
            cfg=self._cfg,
            deadline=deadline,
        )
        if enriched:
            _trace(
                req_id,
                "structured.bot_mimic",
                trigger_reason="structured_rerank",
                chosen_top_k=len(enriched),
                fallback_path="triage_rerank",
            )
            try:
                trust_reg = get_trust_registry()
            except Exception as _e:
                logger.debug("trust_registry unavailable during bot mimic rerank: %s", _e)
                trust_reg = None
            try:
                rep_store = get_reputation_store()
            except Exception as _e:
                logger.debug("reputation_store unavailable during bot mimic rerank: %s", _e)
                rep_store = None

            rank_only = bool(getattr(self._cfg.search, "bot_mimic_only_for_rank_enrichment", True))
            for idx, (title, snippet) in enriched.items():
                enriched_result = replace(
                    deduped[idx],
                    title=title or deduped[idx].title,
                    snippet=snippet or deduped[idx].snippet,
                )
                # Structured rerank should let enriched content compete on its
                # own merits instead of being capped by the provider position.
                enriched_tr = _triage_one_result(
                    enriched_result,
                    query,
                    index=0,
                    total=1,
                    trust_reg=trust_reg,
                    rep_store=rep_store,
                )
                triage[idx] = TriageResult(
                    skip=triage[idx].skip and enriched_tr.skip,
                    fetch_policy=enriched_tr.fetch_policy if enriched_tr.score > triage[idx].score else triage[idx].fetch_policy,
                    score=max(triage[idx].score, enriched_tr.score),
                )
                if not rank_only:
                    deduped[idx].title = enriched_result.title
                    deduped[idx].snippet = enriched_result.snippet

        ranked: list[SearchResult] = []
        skipped: list[SearchResult] = []
        for result, tr in zip(deduped, triage):
            result.score = tr.score
            result.method_hint = tr.fetch_policy
            if tr.skip:
                skipped.append(result)
            else:
                ranked.append(result)

        ranked.sort(key=lambda r: (float(r.score or 0.0), len(r.snippet or "")), reverse=True)
        skipped.sort(key=lambda r: (float(r.score or 0.0), len(r.snippet or "")), reverse=True)
        combined = ranked + skipped
        top_k = _effective_output_limit(out_profile, opts)
        _trace(req_id, "structured.done", chosen_top_k=top_k, skipped=len(skipped), ranked=len(ranked))
        return combined[:top_k]

    async def search_rich(
        self,
        query: str,
        deadline: float | None = None,
    ) -> SearchRichResult:
        """Run web search and return a UI/model friendly structured payload.

        Mirrors search() pipeline step-for-step:
          _run_search_pipeline → pre-fetch _adapt_output_profile (updates preview_fetch_limit)
          → triage-aware to_fetch list → _fetch_previews → post-fetch _adapt_output_profile
          → bot_mimic enrichment (AFTER fetch, like search()) → background prefetch
        Skip/fetch_policy decisions from the triage system are fully honoured.
        """
        opts = self._opts
        search_id = f"srch_{_make_request_id()}"

        # --- 1. Query normalisation (mirrors search() / search_structured()) ---
        constraints = parse_domain_constraints(query)
        analysis_query = constraints.clean_query or query
        analysis_query, _ = _apply_year_hint_policy(analysis_query, self._cfg.query)
            preview_settings = get_preview_settings(apply_hardware_profile=False)
            fetched = await _fetch_previews(
                to_fetch,
                query=query,
                concurrency=self._opts.concurrency,
                fetch_timeout=self._opts.fetch_timeout,
                total_timeout=self._opts.total_timeout,
                preview_settings=preview_settings,
                loop=asyncio.get_running_loop(),
                policies=[result.method_hint or "cheap" for result in to_fetch],
                early_return_threshold=max(0, int(self._cfg.search.early_return_threshold)),
                req_id=search_id,
                deadline=deadline,
            )
            for idx, payload in enumerate(fetched):
                payloads[idx] = payload

        sources = [
            _source_from_result(
                result,
                rank,
                source_id=_citation_source_id(search_id, rank),
                score=result.score,
                preview=payloads[rank - 1].text if rank - 1 < len(payloads) else "",
            )
            for rank, result in enumerate(results, 1)
        ]
        model_context = _build_model_context(query, sources)
        _trace(req_id, "rich.done", sources=len(sources))
        return SearchRichResult(
            query=query,
            search_id=search_id,
            sources=sources,
            model_context=model_context,
            ui={
                "status": "done",
                "result_count": len(sources),
                "compact": _build_compact_ui(query, sources),
            },
        )


# ---------------------------------------------------------------------------
# Top-level convenience coroutine
# ---------------------------------------------------------------------------

# Hard wall-clock limit for the entire search lifecycle.
# When exceeded, the coroutine is cancelled → subprocesses are killed via
# their finally blocks in async_ddgs_search(), aiohttp sessions are closed
# by their async context managers, and executor threads run to natural
# completion (they have internal timeouts so they won't hang indefinitely).
_SEARCH_HARD_TIMEOUT: float = 20.0


async def run_web_search(
    query: str,
    max_results: int = 10,
    fetch_previews: bool = True,
    timelimit: Optional[str] = None,
    time_range: Optional[str] = None,
    hard_timeout: float = _SEARCH_HARD_TIMEOUT,
) -> str:
    """Convenience entry point for MCP adapter and CLI.

    Enforces a hard_timeout (default 20s) over the entire search lifecycle.
    If exceeded, kills spawned subprocesses and returns a clean timeout message
    instead of raising — callers never see a hanging coroutine.

    The time window is inferred automatically from the query type:
      journalistic / finance  → last month
      shopping / troubleshoot / forum / technical → last year
      academic / medical / general → no restriction
    """
    init_t0 = time.perf_counter()
    cfg = load_search_config()
    constraints = parse_domain_constraints(query)
    query_for_search = constraints.clean_query or query
    query_for_search, year_tl = _apply_year_hint_policy(query_for_search, cfg.query)
    # Type-based timelimit: inferred from query classification.
    type_tl = _auto_timelimit(infer_query_types(query_for_search))
    # Use the more restrictive of the two signals.
    auto_timelimit = _stricter_timelimit(year_tl, type_tl)
    explicit_timelimit = (
        _normalize_time_range(time_range)
        or _normalize_time_range(timelimit)
        or timelimit
    )
    resolved_timelimit = explicit_timelimit or auto_timelimit
    opts = WebSearchOptions(
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
        deadline = loop.time() + hard_timeout
        return await asyncio.wait_for(service.search(query, deadline=deadline), timeout=hard_timeout)
    except asyncio.TimeoutError:
        elapsed = round(time.perf_counter() - init_t0, 1)
        logger.warning(
            "web_search.hard_timeout query=%r elapsed=%.1fs limit=%.0fs",
            query[:80], elapsed, hard_timeout,
        )
        return f"Search timed out after {elapsed}s (limit {hard_timeout:.0f}s) for: {query_for_search}"


async def run_web_search_structured(
    query: str,
    max_results: int = 10,
    timelimit: Optional[str] = None,
    hard_timeout: float = _SEARCH_HARD_TIMEOUT,
    time_range: Optional[str] = None,
) -> list[SearchResult]:
    """Structured counterpart to run_web_search for structured callers."""
    cfg = load_search_config()
    constraints = parse_domain_constraints(query)
    query_for_search = constraints.clean_query or query
    query_for_search, year_tl = _apply_year_hint_policy(query_for_search, cfg.query)
    type_tl = _auto_timelimit(infer_query_types(query_for_search))
    auto_timelimit = _stricter_timelimit(year_tl, type_tl)
    explicit_timelimit = (
        _normalize_time_range(time_range)
        or _normalize_time_range(timelimit)
        or timelimit
    )
    resolved_timelimit = explicit_timelimit or auto_timelimit
    opts = WebSearchOptions(
        max_results=max_results,
        fetch_previews=False,
        timelimit=resolved_timelimit,
    )
    service = WebSearchService(options=opts)
    loop = asyncio.get_event_loop()
    deadline = loop.time() + hard_timeout
    try:
        return await asyncio.wait_for(
            service.search_structured(query, deadline=deadline),
            timeout=hard_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "web_search_structured.hard_timeout query=%r limit=%.0fs",
            query[:80], hard_timeout,
        )
        return []


async def run_web_search_rich(
    query: str,
    max_results: int = 10,
    timelimit: Optional[str] = None,
    hard_timeout: float = _SEARCH_HARD_TIMEOUT,
    time_range: Optional[str] = None,
) -> dict[str, object]:
    """Structured web-search payload for MCP structuredContent/UI clients."""
    cfg = load_search_config()
    constraints = parse_domain_constraints(query)
    query_for_search = constraints.clean_query or query
    query_for_search, year_tl = _apply_year_hint_policy(query_for_search, cfg.query)
    type_tl = _auto_timelimit(infer_query_types(query_for_search))
    auto_timelimit = _stricter_timelimit(year_tl, type_tl)
    explicit_timelimit = (
        _normalize_time_range(time_range)
        or _normalize_time_range(timelimit)
        or timelimit
    )
    resolved_timelimit = explicit_timelimit or auto_timelimit
    opts = WebSearchOptions(
        max_results=max_results,
        fetch_previews=True,
        timelimit=resolved_timelimit,
    )
    service = WebSearchService(options=opts)
    loop = asyncio.get_event_loop()
    deadline = loop.time() + hard_timeout
    try:
        rich = await asyncio.wait_for(
            service.search_rich(query.strip(), deadline=deadline),
            timeout=hard_timeout,
        )
        return _rich_result_to_dict(rich)
    except asyncio.TimeoutError:
        logger.warning(
            "web_search_rich.hard_timeout query=%r limit=%.0fs",
            query[:80], hard_timeout,
        )
        search_id = f"srch_{_make_request_id()}"
        return {
            "query": query_for_search,
            "search_id": search_id,
            "sources": [],
            "model_context": f"Search timed out after {hard_timeout:.0f}s for: {query_for_search}",
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
