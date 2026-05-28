# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import difflib
import json
import logging
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("Apps.UI.citation_annotations")


MAX_ITEMS = 16
MAX_TEXT_CHARS = 6000
MAX_PREVIEW_CHARS = 400
MAX_PREVIEW_SENTENCES = 2


@dataclass(frozen=True)
class CitationAnnotationConfig:
    enabled: bool
    reranker_enabled: bool
    reranker_model_dir: str
    reranker_weight: float
    reranker_min_score: float
    idle_ttl_seconds: float
    max_items: int


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _module_bool_setting(env_name: str, settings_key: str, *, default: bool) -> bool:
    """Read a boolean from ASLM_* env when set, otherwise Settings/settings.json."""
    if os.getenv(env_name) is not None:
        return _env_bool(env_name, default)
    try:
        from Settings.settings import get

        return bool(get(settings_key, default))
    except Exception:
        return default


def _default_reranker_model_dir() -> str:
    return str(Path(__file__).resolve().parents[2] / "Tools" / "mcp-web-search" / "models" / "gte_evidence_reranker_full_ft")


def load_config() -> CitationAnnotationConfig:
    reranker_dir = os.getenv("ASLM_GTE_EVIDENCE_RERANKER_DIR", "").strip() or _default_reranker_model_dir()
    alignment_enabled = _module_bool_setting(
        "ASLM_CITATION_ALIGNMENT_ENABLED",
        "citation-alignment-enabled",
        default=False,
    )
    return CitationAnnotationConfig(
        enabled=alignment_enabled,
        reranker_enabled=alignment_enabled
        and _env_bool("ASLM_CITATION_RERANKER_ENABLED", True),
        reranker_model_dir=reranker_dir,
        reranker_weight=float(os.getenv("ASLM_CITATION_RERANKER_WEIGHT", "8.0")),
        reranker_min_score=float(os.getenv("ASLM_CITATION_RERANKER_MIN_SCORE", "0.28")),
        idle_ttl_seconds=float(os.getenv("ASLM_CITATION_IDLE_TTL_SECONDS", "240")),
        max_items=max(1, min(MAX_ITEMS, int(os.getenv("ASLM_CITATION_MAX_ITEMS", "8")))),
    )


def _mcp_tools_path() -> Path:
    return Path(__file__).resolve().parents[2] / "Tools" / "mcp-web-search"


def _get_reranker_runtime() -> Any:
    tools_path = _mcp_tools_path()
    if str(tools_path) not in sys.path:
        sys.path.insert(0, str(tools_path))
    from core.query.gte_evidence_reranker import runtime as reranker_runtime

    return reranker_runtime


def _reranker_inprocess_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def _resolve_mcp_web_search_python() -> Path:
    """Locate the mcp-web-search venv Python (torch + sentence-transformers)."""
    from Services import venv_manager

    explicit = os.getenv("ASLM_MCP_WEB_SEARCH_PYTHON", "").strip()
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return path

    tool_python = venv_manager.get_tool_python("mcp-web-search")
    if tool_python is not None:
        return tool_python

    # Some installs keep a second tree at Projects/ASLM/Modules/ASLM-Chat.
    project_root = Path(__file__).resolve().parents[2]
    alt_root = project_root.parent / "ASLM" / "Modules" / "ASLM-Chat"
    scripts = "Scripts" if os.name == "nt" else "bin"
    exe = "python.exe" if os.name == "nt" else "python"
    alt_python = alt_root / "Data" / "venvs" / "tools" / "mcp-web-search" / scripts / exe
    if alt_python.is_file():
        return alt_python

    return venv_manager.get_venv_python("mcp-web-search")


def _reranker_scores_via_tool_venv(
    claim: str,
    sentences: list[str],
    config: CitationAnnotationConfig,
) -> list[float]:
    """Run GTE in the mcp-web-search venv (has torch + sentence-transformers)."""
    python = _resolve_mcp_web_search_python()
    if not python.is_file():
        raise FileNotFoundError(
            f"mcp-web-search venv python not found: {python}. "
            "Run first-time setup or set ASLM_MCP_WEB_SEARCH_PYTHON."
        )

    tools_path = _mcp_tools_path()
    script = tools_path / "core" / "query" / "gte_score_stdio.py"
    if not script.is_file():
        raise FileNotFoundError(f"GTE stdio bridge missing: {script}")

    payload = json.dumps(
        {
            "claim": claim,
            "sentences": sentences,
            "model_dir": config.reranker_model_dir or None,
            "ttl_seconds": config.idle_ttl_seconds,
        },
        ensure_ascii=False,
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tools_path) + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [str(python), str(script)],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=max(30.0, float(os.getenv("ASLM_CITATION_RERANKER_TIMEOUT", "120"))),
        env=env,
        cwd=str(tools_path),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(detail or f"GTE subprocess exited {result.returncode}")

    data = json.loads(result.stdout or "{}")
    if not data.get("ok"):
        raise RuntimeError(str(data.get("error") or "GTE subprocess returned ok=false"))

    scores = data.get("scores")
    if not isinstance(scores, list) or len(scores) != len(sentences):
        raise RuntimeError("GTE subprocess returned invalid scores payload")

    top = float(data.get("topScore") or max((float(s) for s in scores), default=0.0))
    logger.info(
        "GTE citation rerank via mcp-web-search venv: pairs=%d top_score=%.4f",
        len(scores),
        top,
    )
    return [float(s) for s in scores]


_last_reranker_status: dict[str, Any] = {
    "enabled": False,
    "used": False,
    "backend": "none",
    "topScore": 0.0,
    "error": "",
}


def reranker_status_snapshot() -> dict[str, Any]:
    """Copy of the last GTE call status (for API diagnostics)."""
    return dict(_last_reranker_status)


def _reranker_scores(claim: str, sentences: list[str], config: CitationAnnotationConfig) -> list[float]:
    zeros = [0.0 for _ in sentences]
    if not config.reranker_enabled or not sentences:
        _last_reranker_status.update(
            {"enabled": config.reranker_enabled, "used": False, "backend": "disabled", "topScore": 0.0, "error": ""}
        )
        return zeros

    _last_reranker_status["enabled"] = True
    try:
        if _reranker_inprocess_available():
            runtime = _get_reranker_runtime()
            model_dir = Path(config.reranker_model_dir) if config.reranker_model_dir else None
            scores = runtime.score_evidence(
                claim,
                sentences,
                model_dir=model_dir,
                ttl_seconds=config.idle_ttl_seconds,
            )
            backend = "inprocess"
        else:
            scores = _reranker_scores_via_tool_venv(claim, sentences, config)
            backend = "mcp-web-search-venv"

        top = max((float(s) for s in scores), default=0.0)
        _last_reranker_status.update(
            {"used": top > 0.0, "backend": backend, "topScore": round(top, 4), "error": ""}
        )
        logger.info("GTE citation rerank backend=%s top_score=%.4f", backend, top)
        return scores
    except Exception as exc:
        logger.warning("_reranker_scores failed: %s", exc, exc_info=True)
        _last_reranker_status.update(
            {"used": False, "backend": "failed", "topScore": 0.0, "error": str(exc)}
        )
        return zeros


def unload_citation_models() -> None:
    if not _reranker_inprocess_available():
        return
    try:
        _get_reranker_runtime().unload()
    except Exception:
        pass


def _compact_text(value: Any, limit: int = MAX_TEXT_CHARS) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _normalize_surface(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n.,;:!?\"'")





def _canonical_text(value: str) -> str:
    """Return lowercase alphanumeric characters with all spaces and punctuation stripped."""
    return re.sub(r"[^\w]+", "", str(value or "").casefold(), flags=re.UNICODE)


def _contains_text(haystack: str, needle: str) -> bool:
    needle_canon = _canonical_text(needle)
    if not needle_canon:
        return False
    if len(needle_canon) < 4:
        return _matchable_text(needle) in _matchable_text(haystack)
    return needle_canon in _canonical_text(haystack)


def _matchable_text(value: str) -> str:
    return re.sub(r"[^\w$%.]+", " ", str(value or "").casefold(), flags=re.UNICODE).strip()





def _sentence_chunks(text: str) -> list[str]:
    # Split on: sentence-ending punctuation + whitespace, newlines, space after closing «».
    chunks = re.split(r"(?<=[.!?])\s+|\n+|(?<=»)\s+", text)
    return [_normalize_surface(chunk) for chunk in chunks if len(_normalize_surface(chunk)) >= 12]


def _number_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    pattern = re.compile(
        r"(?:[$€₽]\s*)?\d+(?:[.,]\d+)?(?:\s*/\s*[0-9a-zа-яё$€₽%.-]+)?|\d+(?:[.,]\d+)?\s*[%％]",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(str(text or "")):
        token = re.sub(r"\s+", "", match.group(0)).casefold().replace(",", ".")
        if token and not re.fullmatch(r"\d", token):
            tokens.add(token)
    return tokens


def _is_highlight_worthy_number(token: str) -> bool:
    text = str(token or "").strip()
    if not text:
        return False
    # Currency and percentage symbols are always valuable.
    if re.search(r"[$€₽%％]", text):
        return True
    # Decimal numbers are valuable.
    if re.search(r"\d[.,]\d", text):
        return True
    # Bare years (2020-2030) are rarely valuable as citation highlights.
    digits = re.sub(r"\D", "", text)
    if re.fullmatch(r"20[12]\d", digits):
        return False
    # Numbers with 3+ digits are valuable.
    return len(digits) >= 3


def _shared_number_matches(paragraph: str, source_text: str) -> list[dict[str, Any]]:
    shared = _number_tokens(paragraph) & _number_tokens(source_text)
    return [
        {"type": "number", "text": token}
        for token in sorted(shared, key=len, reverse=True)
        if _is_highlight_worthy_number(token)
    ][:8]


def _sentence_score(sentence: str, paragraph: str) -> float:
    sentence_key = _matchable_text(sentence)
    paragraph_key = _matchable_text(paragraph)
    if not sentence_key or not paragraph_key:
        return 0.0

    score = 0.0
    if sentence_key in paragraph_key or paragraph_key in sentence_key:
        score += 8.0

    shared_numbers = _number_tokens(sentence) & _number_tokens(paragraph)
    score += len(shared_numbers) * 3.0

    score += difflib.SequenceMatcher(None, sentence_key, paragraph_key).ratio() * 2.0
    return score


def _bm25_tokens(text: str) -> list[str]:
    return re.findall(r"[\w$%.]+", _matchable_text(text), flags=re.UNICODE)


def _bm25_query_tokens(paragraph: str) -> list[str]:
    tokens = _bm25_tokens(paragraph)
    for number in _number_tokens(paragraph):
        tokens.extend([number] * 4)
    return tokens


def _bm25_sentence_scores(sentences: list[str], query_tokens: list[str]) -> list[float]:
    if not sentences or not query_tokens:
        return [0.0 for _ in sentences]

    docs = [_bm25_tokens(sentence) for sentence in sentences]
    avgdl = sum(len(doc) for doc in docs) / max(1, len(docs))
    df: dict[str, int] = {}
    for doc in docs:
        for token in set(doc):
            df[token] = df.get(token, 0) + 1

    query_tf: dict[str, int] = {}
    for token in query_tokens:
        query_tf[token] = query_tf.get(token, 0) + 1

    k1 = 1.4
    b = 0.72
    scores: list[float] = []
    for sentence, doc in zip(sentences, docs, strict=True):
        doc_len = max(1, len(doc))
        tf: dict[str, int] = {}
        for token in doc:
            tf[token] = tf.get(token, 0) + 1
        score = 0.0
        for token, q_weight in query_tf.items():
            freq = tf.get(token, 0)
            if not freq:
                continue
            idf = math.log(1 + (len(docs) - df.get(token, 0) + 0.5) / (df.get(token, 0) + 0.5))
            denom = freq + k1 * (1 - b + b * doc_len / max(1.0, avgdl))
            score += min(q_weight, 5) * idf * (freq * (k1 + 1) / denom)
        score += _sentence_score(sentence, " ".join(query_tokens)) * 0.25
        scores.append(score)
    return scores


def _best_sentence(text: str, paragraph: str) -> tuple[str, float]:
    sentences = _sentence_chunks(text)
    bm25_scores = _bm25_sentence_scores(sentences, _bm25_query_tokens(paragraph))
    best_sentence = ""
    best_score = 0.0
    for sentence, bm25_score in zip(sentences, bm25_scores, strict=False):
        score = bm25_score + _sentence_score(sentence, paragraph)
        if score > best_score:
            best_sentence = sentence
            best_score = score
    return best_sentence, best_score


def _top_sentences(
    text: str,
    paragraph: str,
    *,
    config: CitationAnnotationConfig,
    limit: int = 4,
    min_score: float = 3.0,
) -> list[dict[str, Any]]:
    sentences = _sentence_chunks(text)
    bm25_scores = _bm25_sentence_scores(sentences, _bm25_query_tokens(paragraph))
    rerank_scores = _reranker_scores(paragraph, sentences, config)
    scored: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, (sentence, bm25_score, rerank_score) in enumerate(zip(sentences, bm25_scores, rerank_scores, strict=False)):
        score = bm25_score + _sentence_score(sentence, paragraph) + rerank_score * config.reranker_weight
        key = _matchable_text(sentence)
        rerank_hit = config.reranker_enabled and rerank_score >= config.reranker_min_score
        if key and key not in seen and (score >= min_score or rerank_hit):
            seen.add(key)
            scored.append({"index": index, "text": sentence, "score": round(score, 3)})
    return _merge_contiguous_sentence_hits(scored, limit=limit)


def _merge_contiguous_sentence_hits(
    scored: list[dict[str, Any]],
    *,
    limit: int,
    max_merged_chars: int = 200,
) -> list[dict[str, Any]]:
    if not scored:
        return []
    by_index = sorted(scored, key=lambda item: int(item["index"]))
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    previous_index: int | None = None
    for item in by_index:
        index = int(item["index"])
        candidate = _join_sentence_group([*(str(part["text"]) for part in current), str(item["text"])])
        can_merge = previous_index is not None and index == previous_index + 1 and len(candidate) <= max_merged_chars
        if previous_index is None or can_merge:
            current.append(item)
        else:
            groups.append(current)
            current = [item]
        previous_index = index
    if current:
        groups.append(current)

    merged = []
    for group in groups:
        text = _join_sentence_group([str(item["text"]) for item in group])
        score = sum(float(item["score"]) for item in group)
        merged.append({"index": int(group[0]["index"]), "text": text, "score": round(score, 3)})
    merged.sort(key=lambda item: float(item["score"]), reverse=True)
    return merged[:limit]


def _join_sentence_group(sentences: list[str]) -> str:
    joined = ""
    for sentence in sentences:
        clean = sentence.strip()
        if not clean:
            continue
        if joined and not re.search(r"[.!?;:»\"]$", joined):
            joined += "."
        joined = f"{joined} {clean}".strip()
    return joined


def _top_paragraph_sentences(
    paragraph: str,
    source_sentences: list[str],
    matches: list[dict[str, Any]],
    *,
    config: CitationAnnotationConfig,
    source_text: str = "",
    limit: int = 4,
) -> list[str]:
    needles = [*source_sentences, *[str(match.get("text") or "") for match in matches]]
    paragraph_chunks = _sentence_chunks(paragraph)
    rerank_anchor = source_sentences[0] if source_sentences else _compact_text(source_text, 600)
    rerank_scores = _reranker_scores(rerank_anchor, paragraph_chunks, config)
    scored: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, sentence in enumerate(paragraph_chunks):
        score = 0.0
        sentence_key = _matchable_text(sentence)
        sentence_canon = _canonical_text(sentence)
        for needle in needles:
            needle_key = _matchable_text(needle)
            needle_canon = _canonical_text(needle)
            if needle_canon and len(needle_canon) >= 6 and (
                needle_canon in sentence_canon or sentence_canon in needle_canon
            ):
                score += 5.0
            elif needle_key and (needle_key in sentence_key or sentence_key in needle_key):
                score += 3.0
            score += len(_number_tokens(sentence) & _number_tokens(needle)) * 3.0
            if needle_key:
                score += difflib.SequenceMatcher(None, sentence_key, needle_key).ratio()
        if index < len(rerank_scores):
            score += rerank_scores[index] * config.reranker_weight
        rerank_hit = config.reranker_enabled and index < len(rerank_scores) and rerank_scores[index] >= config.reranker_min_score
        if sentence_key and sentence_key not in seen and (score >= 2.0 or rerank_hit):
            seen.add(sentence_key)
            scored.append({"index": index, "text": sentence, "score": round(score, 3)})
    merged = _merge_contiguous_sentence_hits(scored, limit=limit, max_merged_chars=200)
    return [str(item["text"]) for item in merged if len(str(item["text"])) <= 320]


def _direct_quote_matches(paragraph: str, source_text: str) -> list[str]:
    source_canon = _canonical_text(source_text)
    if not source_canon:
        return []
    matches: list[str] = []
    seen: set[str] = set()
    # Use casefolded originals for SequenceMatcher so indices map correctly.
    source_lower = source_text.casefold()
    for chunk in _sentence_chunks(paragraph):
        chunk_canon = _canonical_text(chunk)
        if not chunk_canon or len(chunk_canon) < 12 or chunk_canon in seen:
            continue
        if chunk_canon in source_canon:
            seen.add(chunk_canon)
            matches.append(chunk)
            continue
        # Match in casefold-space so indices correspond to the original chunk.
        chunk_lower = chunk.casefold()
        best = difflib.SequenceMatcher(
            None, chunk_lower, source_lower
        ).find_longest_match(0, len(chunk_lower), 0, len(source_lower))
        min_size = max(18, min(80, int(len(chunk_lower) * 0.45)))
        if best.size >= min_size:
            quote = _normalize_surface(chunk[best.a : best.a + best.size])
            quote_canon = _canonical_text(quote)
            if quote_canon and len(quote_canon) >= 12 and quote_canon not in seen:
                seen.add(quote_canon)
                matches.append(quote)
    return matches[:10]


def annotate_citations(items: list[dict[str, Any]], *, config: CitationAnnotationConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    if not cfg.enabled:
        return {"enabled": False, "annotations": []}

    annotations: list[dict[str, Any]] = []
    for item in items[: cfg.max_items]:
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        source_text = _compact_text(
            source.get("text")
            or source.get("preview")
            or source.get("snippet")
            or source.get("content")
            or source.get("summary")
            or ""
        )
        paragraph = _compact_text(item.get("paragraph_text") or item.get("paragraph") or "")
        citation_id = str(item.get("id") or "").strip()
        annotation_id = str(item.get("annotation_id") or "").strip()
        if not citation_id or not source_text or not paragraph:
            annotations.append(
                {
                    "id": citation_id,
                    "annotation_id": annotation_id,
                    "status": "fallback",
                    "matches": [],
                }
            )
            continue

        quotes = _direct_quote_matches(paragraph, source_text)

        source_sentence_items = _top_sentences(source_text, paragraph, config=cfg)
        source_sentences = [str(item["text"]) for item in source_sentence_items]
        matches = [
            *[{"type": "quote", "text": quote} for quote in quotes],
            *_shared_number_matches(paragraph, source_text),
        ]
        for source_sentence in reversed(source_sentences):
            matches.insert(0, {"type": "source_sentence", "text": source_sentence})
        paragraph_sentences = _top_paragraph_sentences(
            paragraph,
            source_sentences,
            matches,
            config=cfg,
            source_text=source_text,
        )
        for paragraph_sentence in reversed(paragraph_sentences):
            matches.insert(0, {"type": "paragraph_sentence", "text": paragraph_sentence})

        # Build preview from source sentences only — the card shows what the source says,
        # not a rephrasing from the model response.  Canonical deduplication prevents
        # the same sentence appearing twice when a quote and a source_sentence differ
        # only in surrounding « » quotation marks.
        preview_parts: list[str] = []
        seen_preview_canon: set[str] = set()

        def _add_preview_part(text: str) -> bool:
            canon = _canonical_text(text)
            if not canon or canon in seen_preview_canon:
                return False
            seen_preview_canon.add(canon)
            preview_parts.append(text)
            return True

        for sentence in source_sentences[:MAX_PREVIEW_SENTENCES]:
            _add_preview_part(sentence)

        # Fallback: nothing from source → try a direct quote, then raw source_text.
        if not preview_parts:
            for quote in quotes[:1]:
                if _add_preview_part(quote):
                    break
        if not preview_parts and source_text:
            _add_preview_part(_compact_text(source_text, MAX_PREVIEW_CHARS))

        preview_text = "\n".join(preview_parts)
        if len(preview_text) > MAX_PREVIEW_CHARS:
            preview_text = preview_text[:MAX_PREVIEW_CHARS - 3].rsplit(" ", 1)[0] + "..."

        annotations.append(
            {
                "id": citation_id,
                "annotation_id": annotation_id,
                "status": "ready" if matches else "fallback",
                "matches": matches,
                "sourceSentence": source_sentences[0] if source_sentences else "",
                "sourceSentences": source_sentences,
                "paragraphSentence": paragraph_sentences[0] if paragraph_sentences else "",
                "paragraphSentences": paragraph_sentences,
                "previewText": preview_text,
            }
        )

    return {
        "enabled": True,
        "annotations": annotations,
        "reranker": reranker_status_snapshot(),
    }
