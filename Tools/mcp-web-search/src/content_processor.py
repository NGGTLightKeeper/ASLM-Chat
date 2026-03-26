from __future__ import annotations

import html as html_lib
import importlib.util
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


_ROOT_DIR = Path(__file__).resolve().parents[1]
_DEEP_RESEARCH_DIR = _ROOT_DIR / "deep-research"
if _DEEP_RESEARCH_DIR.exists():
    deep_research_path = str(_DEEP_RESEARCH_DIR)
    if deep_research_path not in sys.path:
        sys.path.insert(0, deep_research_path)

_CONFIG_PATH = _ROOT_DIR / "config.py"
_CONFIG_SPEC = importlib.util.spec_from_file_location("_mcp_web_search_preview_config", _CONFIG_PATH)
if _CONFIG_SPEC is None or _CONFIG_SPEC.loader is None:
    raise ImportError(f"Failed to load shared config module from {_CONFIG_PATH}")
_CONFIG_MODULE = importlib.util.module_from_spec(_CONFIG_SPEC)
sys.modules[_CONFIG_SPEC.name] = _CONFIG_MODULE
_CONFIG_SPEC.loader.exec_module(_CONFIG_MODULE)


_BALANCED_DEFAULTS = {
    "output_chars": 1400,
    "min_clean_chars": 220,
    "input_char_limit": 15000,
    "top_k": 3,
    "fetch_timeout": 6.0,
    "total_timeout": 12.0,
    "concurrency": 4,
    "rerank": "soft",
    "enable_gliner": False,
    "gliner_tiers": ("hardened", "fortress"),
    "gliner_max_chars": 2500,
    "gliner_max_entities": 8,
    "gliner_trigger_min_score": 0.18,
}

_PROFILE_DEFAULTS = {
    "speed": {
        "output_chars": 900,
        "min_clean_chars": 180,
        "input_char_limit": 8000,
        "top_k": 2,
        "fetch_timeout": 4.5,
        "total_timeout": 8.0,
        "concurrency": 4,
        "rerank": "off",
        "enable_gliner": False,
        "gliner_tiers": ("hardened", "fortress"),
        "gliner_max_chars": 1600,
        "gliner_max_entities": 6,
        "gliner_trigger_min_score": 0.22,
    },
    "balanced": dict(_BALANCED_DEFAULTS),
    "quality": {
        "output_chars": 1800,
        "min_clean_chars": 260,
        "input_char_limit": 22000,
        "top_k": 4,
        "fetch_timeout": 8.0,
        "total_timeout": 16.0,
        "concurrency": 4,
        "rerank": "soft",
        "enable_gliner": True,
        "gliner_tiers": ("moderate", "hardened", "fortress"),
        "gliner_max_chars": 3200,
        "gliner_max_entities": 10,
        "gliner_trigger_min_score": 0.16,
    },
}

_SETTING_ATTRS = {
    "output_chars": "WEB_SEARCH_PREVIEW_OUTPUT_CHARS",
    "min_clean_chars": "WEB_SEARCH_PREVIEW_MIN_CLEAN_CHARS",
    "input_char_limit": "WEB_SEARCH_PREVIEW_INPUT_CHAR_LIMIT",
    "top_k": "WEB_SEARCH_PREVIEW_TOP_K",
    "fetch_timeout": "WEB_SEARCH_PREVIEW_FETCH_TIMEOUT",
    "total_timeout": "WEB_SEARCH_PREVIEW_TOTAL_TIMEOUT",
    "concurrency": "WEB_SEARCH_PREVIEW_CONCURRENCY",
    "rerank": "WEB_SEARCH_PREVIEW_RERANK",
    "enable_gliner": "WEB_SEARCH_PREVIEW_ENABLE_GLINER",
    "gliner_tiers": "WEB_SEARCH_PREVIEW_GLINER_TIERS",
    "gliner_max_chars": "WEB_SEARCH_PREVIEW_GLINER_MAX_CHARS",
    "gliner_max_entities": "WEB_SEARCH_PREVIEW_GLINER_MAX_ENTITIES",
    "gliner_trigger_min_score": "WEB_SEARCH_PREVIEW_GLINER_TRIGGER_MIN_SCORE",
}

_NOISE_TAGS = {
    "script",
    "style",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "iframe",
    "svg",
    "picture",
    "img",
    "video",
    "source",
    "canvas",
    "button",
    "noscript",
    "figure",
    "figcaption",
}
_BLOCK_TAGS = {
    "article",
    "section",
    "main",
    "div",
    "p",
    "li",
    "pre",
    "code",
    "blockquote",
    "td",
    "th",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}
_LEAF_BLOCK_TAGS = {
    "p",
    "li",
    "pre",
    "code",
    "blockquote",
    "td",
    "th",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}
_NOISE_MARKERS = (
    "cookie",
    "consent",
    "gdpr",
    "newsletter",
    "subscribe",
    "sign up",
    "sign-up",
    "advert",
    "sponsored",
    "promo",
    "share",
    "follow us",
    "all rights reserved",
    "accept all",
    "privacy policy",
    "terms of service",
)
_PROTECTED_CONTAINER_TAGS = {"html", "body", "main", "article"}
_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class PreviewPayload:
    text: str = ""
    semantic_score: float = 0.0
    quality_score: float = 0.0
    clean_chars: int = 0
    used_gliner: bool = False
    strategy_used: str = ""


def get_preview_settings() -> dict[str, Any]:
    profile = str(getattr(_CONFIG_MODULE, "WEB_SEARCH_PREVIEW_PROFILE", "balanced") or "balanced").strip().lower()
    if profile not in _PROFILE_DEFAULTS:
        profile = "balanced"
    settings = dict(_PROFILE_DEFAULTS[profile])
    for key, attr in _SETTING_ATTRS.items():
        balanced_default = _BALANCED_DEFAULTS[key]
        value = getattr(_CONFIG_MODULE, attr, balanced_default)
        if profile == "balanced" or value != balanced_default:
            settings[key] = value

    settings["profile"] = profile
    settings["preview_limit"] = max(0, int(getattr(_CONFIG_MODULE, "WEB_SEARCH_PREVIEW_LIMIT", 10) or 0))
    settings["mode"] = str(getattr(_CONFIG_MODULE, "WEB_SEARCH_MODE", "semantic") or "semantic").strip().lower()
    settings["semantic_require_cuda"] = bool(
        getattr(_CONFIG_MODULE, "WEB_SEARCH_SEMANTIC_REQUIRE_CUDA", False)
    )
    settings["semantic_min_score"] = float(
        getattr(_CONFIG_MODULE, "WEB_SEARCH_SEMANTIC_MIN_SCORE", 0.20) or 0.20
    )
    settings["gliner_enabled_effective"] = bool(settings["enable_gliner"])
    settings["gliner_tiers"] = tuple(
        str(tier).strip().lower()
        for tier in (settings["gliner_tiers"] or ())
        if str(tier).strip()
    )
    return settings


def _normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", html_lib.unescape(text or "").replace("\u00a0", " ")).strip(" -|\t\r\n")


def _single_line(text: str) -> str:
    blocks = [_normalize_text(piece) for piece in re.split(r"\n\s*\n", text or "")]
    blocks = [piece for piece in blocks if piece]
    return " | ".join(blocks)


def _regex_html_to_text(raw_html: str) -> str:
    no_js = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html or "", flags=re.IGNORECASE | re.DOTALL)
    no_js = re.sub(r"\s+on\w+=\"[^\"]*\"", "", no_js)
    return _normalize_text(_TAG_RE.sub(" ", no_js))


def _preclean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return raw_html

    soup = BeautifulSoup(raw_html, "html.parser")

    for tag_name in _NOISE_TAGS:
        for node in soup.find_all(tag_name):
            node.decompose()

    for node in soup.find_all(True):
        attrs_map = node.attrs or {}
        attrs = " ".join(
            str(value)
            for key, value in attrs_map.items()
            if key in {"id", "class", "role", "aria-label", "data-testid"}
        ).lower()
        text_preview = _normalize_text(node.get_text(" ", strip=True))[:240].lower()
        attr_hit = any(marker in attrs for marker in _NOISE_MARKERS)
        text_hit = len(text_preview) <= 120 and any(marker in text_preview for marker in _NOISE_MARKERS)
        if attr_hit or text_hit:
            if node.name in _PROTECTED_CONTAINER_TAGS:
                continue
            if len(text_preview) < 300 or node.name not in {"article", "main"}:
                node.decompose()

    return str(soup)


def _extract_text_with_trafilatura(cleaned_html: str) -> str:
    if not cleaned_html:
        return ""
    try:
        import trafilatura
    except Exception:
        return ""

    html_value = cleaned_html.lstrip()
    if html_value[:6].lower().startswith("<?xml"):
        return ""
    try:
        text = trafilatura.extract(
            cleaned_html,
            include_comments=False,
            include_tables=True,
            favor_precision=True,
            deduplicate=True,
            output_format="txt",
        )
    except Exception:
        return ""
    return text or ""


def _extract_text_with_bs4(cleaned_html: str) -> str:
    if not cleaned_html:
        return ""
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return ""

    soup = BeautifulSoup(cleaned_html, "html.parser")
    blocks: list[str] = []
    for node in soup.find_all(_BLOCK_TAGS):
        if node.name not in _LEAF_BLOCK_TAGS and node.find(_LEAF_BLOCK_TAGS):
            continue
        text = node.get_text(separator=" ", strip=True)
        text = _normalize_text(text)
        if len(text) >= 40:
            blocks.append(text)
    if not blocks:
        text = soup.get_text(separator="\n", strip=True)
        return text or ""
    return "\n\n".join(blocks)


def _split_blocks(text: str) -> list[str]:
    pieces = re.split(r"\n\s*\n|(?<=\.)\s{2,}", text or "")
    blocks: list[str] = []
    for piece in pieces:
        normalized = _normalize_text(piece)
        if not normalized:
            continue
        blocks.append(normalized)
    return blocks


def _get_boilerplate_filter():
    try:
        from src.extractor import _is_boilerplate_block  # type: ignore

        return _is_boilerplate_block
    except Exception:
        def _fallback(text: str) -> bool:
            compact = _normalize_text(text).lower()
            if len(compact) < 40:
                return True
            return any(marker in compact for marker in _NOISE_MARKERS)

        return _fallback


def _dedupe_blocks(blocks: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen_exact: set[str] = set()
    seen_signatures: set[str] = set()
    for block in blocks:
        normalized = _normalize_text(block)
        if not normalized:
            continue
        exact_key = normalized.lower()
        if exact_key in seen_exact:
            continue
        tokens = re.findall(r"\w+", exact_key)
        signature = " ".join(tokens[:18])
        if signature and signature in seen_signatures:
            continue
        seen_exact.add(exact_key)
        if signature:
            seen_signatures.add(signature)
        deduped.append(normalized)
    return deduped


def _clean_extracted_text(text: str) -> tuple[str, int]:
    is_boilerplate = _get_boilerplate_filter()
    blocks = _split_blocks(text)
    filtered = [block for block in blocks if not is_boilerplate(block)]
    deduped = _dedupe_blocks(filtered)
    return "\n\n".join(deduped), len(deduped)


def _estimate_quality(text: str, block_count: int) -> float:
    compact = _normalize_text(text)
    if not compact:
        return 0.0
    chars = len(compact)
    alpha_ratio = sum(1 for ch in compact if ch.isalpha() or ch.isspace()) / max(1, chars)
    digit_ratio = sum(1 for ch in compact if ch.isdigit()) / max(1, chars)
    marker_penalty = sum(1 for marker in _NOISE_MARKERS if marker in compact.lower())
    score = 0.0
    score += min(chars / 1200.0, 1.0) * 0.50
    score += min(block_count / 6.0, 1.0) * 0.20
    score += max(0.0, min(alpha_ratio, 1.0)) * 0.25
    score -= min(digit_ratio, 0.20) * 0.20
    score -= min(marker_penalty * 0.08, 0.25)
    return max(0.0, min(round(score, 4), 1.0))


def _semantic_extract(text: str, query: str, settings: dict[str, Any]) -> tuple[str, float]:
    if settings["mode"] != "semantic" or not query.strip():
        return text, 0.0
    try:
        from src.semantic import ensure_embedder_ready, extract_relevant_content  # type: ignore
    except Exception:
        return text, 0.0

    semantic_input = text[: max(0, int(settings["input_char_limit"]))]
    if not semantic_input:
        return text, 0.0
    try:
        ensure_embedder_ready(require_cuda=bool(settings["semantic_require_cuda"]))
        preview_text, scored_chunks = extract_relevant_content(
            text=semantic_input,
            query=query,
            max_chars=max(200, int(settings["output_chars"]) * 2),
            top_k=max(1, int(settings["top_k"])),
            min_score=float(settings["semantic_min_score"]),
        )
    except Exception:
        return text, 0.0

    scores = [float(score) for _, score in (scored_chunks or []) if isinstance(score, (int, float))]
    semantic_score = max(scores) if scores else 0.0
    return preview_text or text, max(0.0, min(round(semantic_score, 4), 1.0))


def _gliner_summary(text: str, query: str, settings: dict[str, Any]) -> tuple[str, bool]:
    if not settings["gliner_enabled_effective"] or not query.strip():
        return "", False
    try:
        from src.gliner_wrapper import (  # type: ignore
            detect_language_and_adjust_threshold,
            extract_entities,
            get_labels_for_query,
        )
    except Exception:
        return "", False

    labels = get_labels_for_query(query)
    if not labels:
        return "", False

    sample = text[: max(200, int(settings["gliner_max_chars"]))]
    if not sample.strip():
        return "", False

    try:
        threshold = detect_language_and_adjust_threshold(sample)
        entities = extract_entities(sample, labels, threshold=threshold, max_length=len(sample))
    except Exception:
        return "", False

    unique: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entity in entities:
        label = _normalize_text(str(entity.get("label", "")))
        value = _normalize_text(str(entity.get("text", "")))
        if not label or not value:
            continue
        key = (label.lower(), value.lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append((label, value))
        if len(unique) >= int(settings["gliner_max_entities"]):
            break

    if not unique:
        return "", False

    rendered = "; ".join(f"{label}: {value}" for label, value in unique)
    return f"Key entities: {rendered}.", True


def warm_preview_models(settings: Optional[dict[str, Any]] = None) -> None:
    active_settings = dict(settings or get_preview_settings())
    if active_settings.get("mode") == "semantic":
        try:
            from src.semantic import ensure_embedder_ready  # type: ignore

            ensure_embedder_ready(require_cuda=bool(active_settings.get("semantic_require_cuda")))
        except Exception:
            pass

    if active_settings.get("gliner_enabled_effective"):
        try:
            from src.gliner_wrapper import _get_model  # type: ignore

            _get_model()
        except Exception:
            pass


def build_preview_payload(
    url: str,
    raw_html: str,
    query: str = "",
    domain_info: Optional[Any] = None,
    settings: Optional[dict[str, Any]] = None,
) -> PreviewPayload:
    active_settings = dict(settings or get_preview_settings())
    cleaned_html = _preclean_html(raw_html)

    strategy_parts: list[str] = []
    extracted = _extract_text_with_trafilatura(cleaned_html)
    if extracted:
        strategy_parts.append("trafilatura")

    if len(_normalize_text(extracted)) < int(active_settings["min_clean_chars"]):
        bs4_text = _extract_text_with_bs4(cleaned_html)
        if len(_normalize_text(bs4_text)) > len(_normalize_text(extracted)):
            extracted = bs4_text
            strategy_parts.append("bs4")

    if len(_normalize_text(extracted)) < int(active_settings["min_clean_chars"]):
        regex_text = _regex_html_to_text(cleaned_html or raw_html)
        if len(regex_text) > len(_normalize_text(extracted)):
            extracted = regex_text
            strategy_parts.append("regex")

    cleaned_text, block_count = _clean_extracted_text(extracted)
    quality_score = _estimate_quality(cleaned_text, block_count)
    preview_text, semantic_score = _semantic_extract(cleaned_text, query, active_settings)
    if preview_text != cleaned_text and preview_text.strip():
        strategy_parts.append("semantic")

    tier = str(getattr(domain_info, "tier", "unknown") or "unknown").strip().lower()
    should_try_gliner = (
        tier in set(active_settings["gliner_tiers"])
        and (
            semantic_score < float(active_settings["gliner_trigger_min_score"])
            or len(_normalize_text(preview_text)) < int(active_settings["min_clean_chars"])
            or quality_score < 0.32
        )
    )
    used_gliner = False
    if should_try_gliner:
        summary, used_gliner = _gliner_summary(cleaned_text or preview_text, query, active_settings)
        if summary:
            preview_text = f"{summary} {preview_text}".strip() if preview_text.strip() else summary
            strategy_parts.append("gliner")

    if not preview_text.strip():
        preview_text = cleaned_text

    compact_preview = _single_line(preview_text)
    output_chars = max(120, int(active_settings["output_chars"]))
    compact_preview = compact_preview[:output_chars].rstrip(" ,;:|-")

    return PreviewPayload(
        text=compact_preview,
        semantic_score=max(0.0, min(float(semantic_score or 0.0), 1.0)),
        quality_score=max(0.0, min(float(quality_score or 0.0), 1.0)),
        clean_chars=len(_normalize_text(cleaned_text)),
        used_gliner=used_gliner,
        strategy_used="+".join(strategy_parts) if strategy_parts else "empty",
    )
