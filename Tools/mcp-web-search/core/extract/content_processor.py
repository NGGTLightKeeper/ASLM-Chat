# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Content processor: extract and score text from raw HTML.

Refactored from legacy src/content_processor.py:
  - Removed all sys.path.insert hacks and importlib.util config loading
  - Profile/settings system replaced by typed core.config.SearchConfig
  - Internal imports (semantic, gliner) use absolute package paths
  - PreviewPayload and build_preview_payload preserved for compatibility

Public API
----------
PreviewPayload    -- dataclass: text + quality/semantic scores
build_preview_payload(url, raw_html, query, settings) -> PreviewPayload
Helper functions (used by page_normalizer and services):
  _preclean_html, _extract_text_with_bs4, _regex_html_to_text,
  _normalize_text, _dedupe_blocks, _get_boilerplate_filter
"""

from __future__ import annotations

import html as html_lib
import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

logger = logging.getLogger("core.extract.content_processor")

# ---------------------------------------------------------------------------
# LaTeX processing: index_text (BM25) and llm_text (model)
# ---------------------------------------------------------------------------

_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+")
_LATEX_SPAN_RE = re.compile(
    r"\$\$.*?\$\$"           # $$...$$
    r"|\\\[.*?\\\]"           # \[...\]
    r"|\\\(.*?\\\)"           # \(...\)
    r"|\$[^$\n]+?\$"          # $...$  (inline, no newline)
    r"|\\[a-zA-Z]+\{[^}]*\}", # \cmd{...}
    re.DOTALL,
)

# Greek letters → Unicode
_GREEK: dict[str, str] = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ",
    "epsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ",
    "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ",
    "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}

# Common symbols → Unicode
_SYMBOLS: dict[str, str] = {
    "cdot": "·", "times": "×", "div": "÷",
    "leq": "≤", "geq": "≥", "neq": "≠", "approx": "≈",
    "infty": "∞", "in": "∈", "notin": "∉",
    "sum": "Σ", "prod": "Π", "int": "∫",
    "pm": "±", "mp": "∓",
    "rightarrow": "→", "leftarrow": "←",
    "Rightarrow": "⇒", "Leftarrow": "⇐",
    "to": "→", "mapsto": "↦",
    "ldots": "...", "cdots": "···", "vdots": "⋮",
    "sqrt": "√",
    # delimiters — stripped
    "left": "", "right": "",
    "big": "", "Big": "", "bigg": "", "Bigg": "",
    # spacing — stripped
    "quad": " ", "qquad": "  ", ",": " ", ";": " ", "!": "",
}


# Macros already handled by _node_to_text or pylatexenc's default context.
# Unknown macros not in this set will be registered as 1-arg pass-through so
# their content is preserved instead of silently dropped.
_KNOWN_MACROS: frozenset[str] = (
    frozenset(_GREEK)
    | frozenset(_SYMBOLS)
    | frozenset({
        "text", "textbf", "textit", "texttt", "textrm",
        "mathrm", "mathbf", "mathit", "mathtt", "mathcal",
        "mathbb", "emph", "operatorname",
        "frac", "sqrt", "sum", "prod", "int",
        "left", "right", "big", "Big", "bigg", "Bigg",
        "quad", "qquad",
        # common LaTeX2e structural macros (no content to preserve)
        "begin", "end", "label", "ref", "cite", "bibitem",
        "footnote", "item", "newline", "noindent", "centering",
        "hline", "cline", "multicolumn", "multirow",
        # math accents / decorators handled by walker pass-through already
        "hat", "bar", "tilde", "vec", "dot", "ddot", "overline",
        "underline", "widehat", "widetilde",
    })
)


def _unknown_macros(text: str) -> list[str]:
    """Return sorted list of \\cmd names in *text* not in _KNOWN_MACROS."""
    found = {m[1:] for m in _LATEX_CMD_RE.findall(text)}
    return sorted(found - _KNOWN_MACROS)


def _make_walker_context(unknown: list[str]):
    """Build a pylatexenc LatexWalker context with unknown macros as 1-arg pass-through.

    Built-in pylatexenc definitions take precedence (prepend=False); our specs
    only apply for macros that pylatexenc genuinely does not know.
    Returns None if pylatexenc API is unavailable or *unknown* is empty.
    The caller should fall back to a plain LatexWalker() when None is returned.
    """
    if not unknown:
        return None
    try:
        from pylatexenc.latexwalker import get_default_latex_context_db
        from pylatexenc.macrospec import MacroSpec
        db = get_default_latex_context_db()
        db.add_context_category(
            "custom_macros",
            macros=[MacroSpec(name, args_parser="{") for name in unknown],
        )
        return db
    except Exception as exc:
        logger.debug("Failed to build LatexWalker context: %s", exc)
        return None


def _make_l2t_context(unknown: list[str]):
    """Build a pylatexenc latex2text context with unknown macros as 1-arg pass-through.

    Built-in pylatexenc definitions take precedence (prepend=False); our specs
    only apply for macros that pylatexenc genuinely does not know.
    Returns None if pylatexenc API is unavailable or *unknown* is empty.
    The caller should fall back to plain LatexNodes2Text() when None is returned.
    """
    if not unknown:
        return None
    try:
        from pylatexenc.latex2text import get_default_latex_context_db, MacroTextSpec
        db = get_default_latex_context_db()
        db.add_context_category(
            "custom_macros",
            macros=[MacroTextSpec(name, simplify_repl="%s") for name in unknown],
        )
        return db
    except Exception as exc:
        logger.debug("Failed to build latex2text context: %s", exc)
        return None


def _has_latex(text: str) -> bool:
    """Quick heuristic: True when text likely contains LaTeX markup."""
    if not text:
        return False
    if "$$" in text or "\\[" in text or "\\(" in text:
        return True
    # Inline math: $...\cmd...$ — must contain a backslash command inside the
    # dollar signs to avoid false positives on plain dollar amounts like "$5".
    if re.search(r'\$[^$\n]*\\[a-zA-Z]+[^$\n]*\$', text):
        return True
    return len(_LATEX_CMD_RE.findall(text)) >= 3


def _clean_latex_for_index(text: str) -> str:
    """Convert LaTeX markup to plain text suitable for BM25 tokenisation.

    Uses pylatexenc.LatexNodes2Text when available; falls back to a simple
    regex stripper so BM25 is never blocked by a missing optional dep.
    Unknown macros are registered as 1-arg pass-through so their content
    is preserved rather than silently dropped.
    """
    if not _has_latex(text):
        return text
    try:
        from pylatexenc.latex2text import LatexNodes2Text
        ctx = _make_l2t_context(_unknown_macros(text))
        l2t = LatexNodes2Text(math_mode="text", latex_context=ctx) if ctx else LatexNodes2Text(math_mode="text")
        return l2t.latex_to_text(text)
    except Exception as exc:
        logger.debug("Latex-to-text conversion failed, using regex fallback: %s", exc)
        pass
    # Regex fallback: unwrap \cmd{content} → content, strip bare \cmd
    cleaned = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", text)
    cleaned = re.sub(r"\\[a-zA-Z]+", " ", cleaned)
    return re.sub(r"[\$\{\}]", " ", cleaned)


def _node_to_text(node) -> str:  # noqa: ANN001
    """Recursively transpile a pylatexenc node to readable text for the LLM."""
    from pylatexenc.latexwalker import (
        LatexCharsNode, LatexMacroNode, LatexGroupNode,
        LatexMathNode, LatexEnvironmentNode, LatexCommentNode,
    )

    if node is None:
        return ""
    if isinstance(node, LatexCharsNode):
        return node.chars

    if isinstance(node, LatexGroupNode):
        return "".join(_node_to_text(n) for n in (node.nodelist or []))

    if isinstance(node, LatexCommentNode):
        return ""

    if isinstance(node, LatexMathNode):
        # Recurse into the math content
        return "".join(_node_to_text(n) for n in (node.nodelist or []))

    if isinstance(node, LatexMacroNode):
        name = node.macroname
        args = node.nodeargd.argnlist if (node.nodeargd and node.nodeargd.argnlist) else []
        rendered_args = [_node_to_text(a) for a in args if a is not None]

        # Greek & symbols
        if name in _GREEK:
            return _GREEK[name]
        if name in _SYMBOLS:
            sym = _SYMBOLS[name]
            # Append rendered args if any (e.g. \sqrt{x} → √x)
            return sym + "".join(rendered_args)

        # Text/formatting wrappers — return inner content only
        if name in {"text", "textbf", "textit", "texttt", "textrm",
                    "mathrm", "mathbf", "mathit", "mathtt", "mathcal",
                    "mathbb", "emph", "operatorname"}:
            return "".join(rendered_args)

        # \frac{a}{b} → (a)/(b)
        if name == "frac" and len(rendered_args) >= 2:
            return f"({rendered_args[0]})/({rendered_args[1]})"

        # \sqrt[n]{x} or \sqrt{x}
        if name == "sqrt":
            if len(rendered_args) == 2:  # optional arg is index
                return f"{rendered_args[0]}√{rendered_args[1]}"
            if rendered_args:
                return f"√{rendered_args[0]}"
            return "√"

        # \sum / \prod / \int with optional limits
        if name in {"sum", "prod", "int"}:
            sym = {"sum": "Σ", "prod": "Π", "int": "∫"}[name]
            return sym + "".join(rendered_args)

        # Superscript/subscript are handled at LatexCharsNode level
        # Bare \cmd with args — render args
        if rendered_args:
            return "".join(rendered_args)
        # Bare \cmd no args
        return ""

    if isinstance(node, LatexEnvironmentNode):
        return "".join(_node_to_text(n) for n in (node.nodelist or []))

    # Fallback: stringify
    return str(getattr(node, "chars", "") or "")


def _render_latex_for_llm(text: str) -> str:
    """Transpile LaTeX markup to human-readable notation for the LLM.

    Walks the entire text through LatexWalker. Plain-text regions become
    LatexCharsNode and pass through unchanged, so non-LaTeX content is safe.
    Only activated when _has_latex() is True (cheap heuristic).
    Unknown macros are registered as 1-arg pass-through so their content
    is preserved rather than silently dropped.
    Falls back gracefully to _clean_latex_for_index when pylatexenc is absent.
    """
    if not _has_latex(text):
        return text

    try:
        from pylatexenc.latexwalker import LatexWalker
        ctx = _make_walker_context(_unknown_macros(text))
        walker = LatexWalker(text, latex_context=ctx) if ctx else LatexWalker(text)
        nodes, _, _ = walker.get_latex_nodes()
        result = "".join(_node_to_text(n) for n in (nodes or [])).strip()
        return result if result else text
    except Exception:
        return _clean_latex_for_index(text)


# ---------------------------------------------------------------------------
# BM25 helpers (no external deps; used for paragraph compression)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\b\w+\b")
_BM25_K1 = 1.5
_BM25_B = 0.75
_BM25_MIN_TOKEN_LEN = 2


def _bm25_tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > _BM25_MIN_TOKEN_LEN]


def _bm25_score_paragraphs(paragraphs: list[str], query_terms: list[str]) -> list[float]:
    """Return BM25 score of each paragraph against query_terms."""
    if not paragraphs or not query_terms:
        return [0.0] * len(paragraphs)

    para_tokens = [_bm25_tokenize(p) for p in paragraphs]
    avg_dl = sum(len(t) for t in para_tokens) / max(1, len(para_tokens))
    N = len(paragraphs)

    df: dict[str, int] = {}
    for term in set(query_terms):
        df[term] = sum(1 for tokens in para_tokens if term in tokens)

    scores: list[float] = []
    for tokens in para_tokens:
        dl = len(tokens)
        tf_map: dict[str, int] = {}
        for t in tokens:
            tf_map[t] = tf_map.get(t, 0) + 1
        score = 0.0
        for term in query_terms:
            tf = tf_map.get(term, 0)
            if tf == 0:
                continue
            idf = math.log((N - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5) + 1)
            tf_norm = (tf * (_BM25_K1 + 1)) / (tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * dl / max(1, avg_dl)))
            score += idf * tf_norm
        scores.append(score)
    return scores


def _should_run_gliner(quality_score: float, hw_profile: str) -> tuple[bool, str]:
    """Return (should_run, device) based on hardware profile and page quality."""
    if hw_profile == "full_gpu":
        # GPU available: densify any page that passed basic quality bar
        return quality_score >= 0.20, "cuda"
    # Limited VRAM / CPU-only: never run GLiNER on CPU.
    return False, ""


def _gliner_compress(
    paragraphs: list[str],
    query_terms: list[str],
    max_chars: int,
    device: str = "cpu",
    query_type: str | None = None,
) -> tuple[str, bool]:
    """Re-rank paragraphs by BM25 + GLiNER entity-density hybrid, fit to max_chars.

    Returns (compressed_text, used_gliner).
    used_gliner=False means GLiNER was unavailable; caller should fall back.
    Hybrid score: 55 % BM25 relevance + 45 % entity density.
    """
    if not paragraphs:
        return "", False

    try:
        from core.extract.gliner_wrapper import get_labels_for_query, score_entity_density_with_entities
        labels = get_labels_for_query(" ".join(query_terms), query_type=query_type)
        gliner_scored = score_entity_density_with_entities(
            paragraphs, labels=labels, device=device,
        )
        gliner_scores = [s for s, _ in gliner_scored]
    except Exception:
        return "", False

    bm25_scores = _bm25_score_paragraphs(paragraphs, query_terms) if query_terms else [0.0] * len(paragraphs)

    max_b = max(bm25_scores) if bm25_scores else 0.0
    bm25_norm = [s / max_b for s in bm25_scores] if max_b > 0 else [0.0] * len(paragraphs)

    hybrid = [0.55 * b + 0.45 * g for b, g in zip(bm25_norm, gliner_scores)]
    ranked = sorted(range(len(paragraphs)), key=lambda i: -hybrid[i])

    selected: set[int] = set()
    budget = max_chars
    for idx in ranked:
        cost = len(paragraphs[idx]) + 2
        if cost <= budget:
            selected.add(idx)
            budget -= cost
        if budget <= 0:
            break

    result = [paragraphs[i] for i in sorted(selected)]
    return ("\n\n".join(result) if result else ""), True


def compress_to_budget(text: str, query: str, max_chars: int) -> str:
    """Select top paragraphs by BM25 relevance that fit within max_chars.

    Runs in O(n*m) time (n paragraphs, m query terms). No GPU required.
    Preserves original paragraph order in the output for readability.
    Falls back to simple truncation when query is empty or text is short.
    """
    if not text or len(text) <= max_chars:
        return text

    paragraphs = _split_blocks(text)
    if not paragraphs:
        return text[:max_chars]

    query_terms = _bm25_tokenize(query)
    if not query_terms:
        # No query terms — greedily take paragraphs from the top
        selected, budget = [], max_chars
        for p in paragraphs:
            cost = len(p) + 2
            if cost <= budget:
                selected.append(p)
                budget -= cost
        return "\n\n".join(selected) if selected else text[:max_chars]

    # Score against LaTeX-clean versions so math notation doesn't confuse
    # tokenisation, but keep original paragraph text for the output.
    if _has_latex(text):
        score_paras = [_clean_latex_for_index(p) for p in paragraphs]
    else:
        score_paras = paragraphs

    scores = _bm25_score_paragraphs(score_paras, query_terms)
    ranked = sorted(range(len(paragraphs)), key=lambda i: -scores[i])

    selected: set[int] = set()
    budget = max_chars
    for idx in ranked:
        cost = len(paragraphs[idx]) + 2
        if cost <= budget:
            selected.add(idx)
            budget -= cost
        if budget <= 0:
            break

    # Reconstruct in original order
    result = [paragraphs[i] for i in sorted(selected)]
    return "\n\n".join(result) if result else text[:max_chars]


def derive_read_page_focus(url: str, markdown: str) -> str:
    """Fallback BM25 query from URL path segments and page title (not for direct use as primary focus)."""
    from urllib.parse import unquote, urlparse

    parts: list[str] = []
    if url:
        parsed = urlparse(url)
        path = unquote(parsed.path or "")
        stop = frozenset({
            "www", "blob", "tree", "raw", "main", "master", "head", "tag", "refs",
            "pull", "issues", "wiki", "html", "htm", "php", "asp", "aspx",
        })
        segments = [
            seg
            for seg in re.split(r"[/._\-]+", path)
            if seg and seg.lower() not in stop and not seg.isdigit()
        ]
        if segments:
            parts.append(" ".join(segments[-5:]))

    for pattern in (r"^#\s+(.+)$", r"^\*\*Title:\*\*\s*(.+)$"):
        match = re.search(pattern, markdown or "", re.MULTILINE | re.IGNORECASE)
        if match:
            title = match.group(1).strip()
            if title:
                parts.append(title)
                break

    return " ".join(parts).strip()


def _resolve_read_page_compress_query(focus: str, url: str, markdown: str) -> str:
    """Prefer explicit focus; otherwise derive from URL/title; else empty (head-truncate in compress_to_budget)."""
    explicit = (focus or "").strip()
    if explicit:
        return explicit
    try:
        return derive_read_page_focus(url, markdown)
    except Exception:
        logger.debug("derive_read_page_focus failed for url=%r", url, exc_info=True)
        return ""


def compress_read_page_markdown(
    markdown: str,
    *,
    url: str = "",
    focus: str = "",
    max_chars: int,
    compress_threshold: int,
    compress_target: int,
    enable_compress: bool = True,
    enable_gliner: bool = False,
) -> str:
    """Shrink long read_page output with BM25 or GLiNER before the hard max_chars cap."""
    text = markdown or ""
    if not text:
        return text

    if enable_compress and compress_threshold > 0 and len(text) > compress_threshold:
        budget = compress_target if compress_target > 0 else max_chars
        budget = min(budget, max_chars)
        query = _resolve_read_page_compress_query(focus, url, text)

        if enable_gliner:
            from core.config.hardware import get_hardware_profile

            blocks = _split_blocks(text)
            quality = _estimate_quality(text, len(blocks))
            run_gliner, device = _should_run_gliner(quality, get_hardware_profile())
            if run_gliner:
                query_terms = _bm25_tokenize(query)
                compressed, used_gliner = _gliner_compress(
                    blocks, query_terms, budget, device=device
                )
                if used_gliner and compressed.strip():
                    text = compressed
                else:
                    text = compress_to_budget(text, query, budget)
            else:
                text = compress_to_budget(text, query, budget)
        else:
            text = compress_to_budget(text, query, budget)

    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0] + "\n\n[...truncated]"
    return text


# ---------------------------------------------------------------------------
# Tag / noise constants
# ---------------------------------------------------------------------------

_NOISE_TAGS = {
    "script", "style", "nav", "header", "footer", "aside", "form",
    "iframe", "svg", "picture", "img", "video", "source", "canvas",
    "button", "noscript", "figure", "figcaption",
}
_BLOCK_TAGS = {
    "article", "section", "main", "div", "p", "li", "pre", "code",
    "blockquote", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6",
}
_LEAF_BLOCK_TAGS = {
    "p", "li", "pre", "code", "blockquote", "td", "th",
    "h1", "h2", "h3", "h4", "h5", "h6",
}
_PROTECTED_CONTAINER_TAGS = {"html", "body", "main", "article"}
_NOISE_MARKERS = (
    "cookie", "consent", "gdpr", "newsletter", "subscribe", "sign up",
    "sign-up", "advert", "sponsored", "promo", "share", "follow us",
    "all rights reserved", "accept all", "privacy policy", "terms of service",
)

_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
_TAG_RE = re.compile(r"<[^>]+>")


# ---------------------------------------------------------------------------
# Preview settings (simple defaults; extended profile support via config)
# ---------------------------------------------------------------------------

_DEFAULT_SETTINGS: dict[str, Any] = {
    "output_chars": 1_400,
    "min_clean_chars": 220,
    "input_char_limit": 15_000,
    "top_k": 3,
    "fetch_timeout": 6.0,
    "total_timeout": 12.0,
    "concurrency": 4,
    "rerank": "soft",
    "mode": "bm25",
    "semantic_require_cuda": False,
    "semantic_min_score": 0.20,
    "enable_gliner": False,
    "gliner_tiers": (),
    "gliner_max_chars": 2_500,
    "gliner_max_entities": 8,
    "gliner_trigger_min_score": 0.18,
    "preview_limit": 10,
    "gliner_enabled_effective": False,
    "profile": "balanced",
}


def get_preview_settings(*, apply_hardware_profile: bool = True) -> dict[str, Any]:
    """Return current preview settings merged with hardware profile defaults."""
    settings = dict(_DEFAULT_SETTINGS)
    try:
        from core.config import load_search_config
        cfg = load_search_config()
        settings["output_chars"] = cfg.search.preview_max_chars
        settings["min_clean_chars"] = cfg.search.preview_min_chars
        settings["preview_limit"] = cfg.search.preview_fetch_limit
        settings["enable_gliner"] = cfg.search.enable_gliner
        settings["gliner_trigger_min_score"] = cfg.search.gliner_trigger_min_score
    except Exception as exc:
        logger.debug("Preview settings config load failed, using built-ins: %s", exc)
        pass

    # Apply hardware-based defaults: enable expensive layers only when GPU
    # has sufficient free VRAM.
    if apply_hardware_profile:
        try:
            from core.config.hardware import get_hardware_profile
            profile = get_hardware_profile()
            if profile == "cpu_safe":
            # No GPU or not enough VRAM — BM25 only, no embedding models
                settings["mode"] = "bm25"
                settings["enable_gliner"] = False
                settings["semantic_require_cuda"] = False
            elif profile == "partial_gpu":
            # Embeddings OK, GLiNER too memory-hungry
                settings["mode"] = "bm25"
                settings["enable_gliner"] = False
                settings["semantic_require_cuda"] = False
            else:
            # full_gpu — all layers available
                settings["mode"] = "bm25"
            # GLiNER still opt-in via config; don't force-enable here
        except Exception as exc:
            logger.debug("Hardware profile detection failed, using default preview mode: %s", exc)
            pass

    return settings


# ---------------------------------------------------------------------------
# PreviewPayload
# ---------------------------------------------------------------------------

@dataclass
class PreviewPayload:
    text: str = ""
    semantic_score: float = 0.0
    quality_score: float = 0.0
    clean_chars: int = 0
    used_gliner: bool = False
    strategy_used: str = ""
    extraction_status: str = ""
    policy_family: str = ""
    chunks_selected: int = 0
    seo_rejected: int = 0
    nav_rejected: int = 0


# ---------------------------------------------------------------------------
# HTML cleaning helpers (used by page_normalizer)
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(
        " ", html_lib.unescape(text or "").replace("\u00a0", " ")
    ).strip(" -|\t\r\n")


def _single_line(text: str) -> str:
    blocks = [_normalize_text(piece) for piece in re.split(r"\n\s*\n", text or "")]
    return " | ".join(block for block in blocks if block)


_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


def _truncate_at_sentence(text: str, max_chars: int) -> str:
    """Truncate *text* to *max_chars*, trying to end on a sentence boundary.

    Strategy:
      1. If text fits — return as-is.
      2. Look for the last sentence-ending punctuation (. ! ?) within the
         budget.  Accept it only when at least 60 % of the budget is used,
         so we don't return a tiny fragment for a page that starts with a
         short sentence.
      3. Fall back to the hard character limit stripped of trailing
         punctuation if no good boundary is found.
    """
    if len(text) <= max_chars:
        return text

    window = text[:max_chars]
    # Find all sentence-end positions inside the window.
    best = -1
    for m in _SENTENCE_END_RE.finditer(window):
        best = m.start()  # position right after the closing punctuation

    min_acceptable = int(max_chars * 0.60)
    if best >= min_acceptable:
        return window[:best].rstrip()

    return window.rstrip(" ,;:|-")


def _regex_html_to_text(raw_html: str) -> str:
    no_js = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html or "",
                   flags=re.IGNORECASE | re.DOTALL)
    no_js = re.sub(r'\s+on\w+="[^"]*"', "", no_js)
    return _normalize_text(_TAG_RE.sub(" ", no_js))


_SERP_REF_ATTR = "data-aslm-serp-ref"
_MIN_SERP_SNIPPET_CHARS = 20
_MIN_SERP_TITLE_CHARS = 12
_MIN_PAGE_TITLE_CHARS = 8
_MIN_META_DESC_CHARS = 24


def _extract_page_title_reference(raw_html: str) -> str:
    """Best-effort page title / description for SEO reference when SERP snippet is absent."""
    if not raw_html:
        return ""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw_html, "html.parser")
        if soup.title and soup.title.string:
            title = _normalize_text(str(soup.title.string))
            if len(title) >= _MIN_PAGE_TITLE_CHARS:
                return title
        for attrs in ({"property": "og:title"}, {"name": "twitter:title"}):
            node = soup.find("meta", attrs=attrs)
            if node and node.get("content"):
                title = _normalize_text(str(node["content"]))
                if len(title) >= _MIN_PAGE_TITLE_CHARS:
                    return title
        desc = soup.find("meta", attrs={"name": "description"})
        if desc and desc.get("content"):
            text = _normalize_text(str(desc["content"]))
            if len(text) >= _MIN_META_DESC_CHARS:
                return text
    except Exception as exc:
        logger.debug("page title reference extraction failed: %s", exc)

    m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, flags=re.IGNORECASE | re.DOTALL)
    if m:
        title = _normalize_text(html_lib.unescape(m.group(1)))
        if len(title) >= _MIN_PAGE_TITLE_CHARS:
            return title
    return ""


def _resolve_serp_reference(
    settings: dict[str, Any],
    raw_html: str,
) -> tuple[str, str]:
    """Resolve SEO/SERP reference text and its source label."""
    snippet = _normalize_text(str(settings.get("serp_snippet") or ""))
    if len(snippet) >= _MIN_SERP_SNIPPET_CHARS:
        return snippet, "serp_snippet"

    serp_title = _normalize_text(str(settings.get("serp_title") or ""))
    if len(serp_title) >= _MIN_SERP_TITLE_CHARS:
        return serp_title, "serp_title"

    page_title = _extract_page_title_reference(raw_html)
    if page_title:
        return page_title, "page_title"
    return "", ""


def _inject_serp_reference_into_html(raw_html: str, reference: str) -> str:
    """Prepend SERP snippet into HTML so extractors can align against it."""
    reference = _normalize_text(reference)
    if not raw_html or not reference:
        return raw_html
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw_html, "html.parser")
        body = soup.body
        if body is None:
            body = soup.new_tag("body")
            if soup.html:
                soup.html.append(body)
            else:
                soup.append(body)
        marker = soup.new_tag("p")
        marker[_SERP_REF_ATTR] = "1"
        marker.string = reference
        body.insert(0, marker)
        return str(soup)
    except Exception as exc:
        logger.debug("serp reference inject failed, using string prepend: %s", exc)
        escaped = html_lib.escape(reference)
        return f'<p {_SERP_REF_ATTR}="1">{escaped}</p>{raw_html}'


def _strip_serp_reference_blocks(text: str, reference: str) -> str:
    """Remove injected or duplicated SERP reference blocks from extracted text."""
    ref_norm = _normalize_text(reference)
    if not text or not ref_norm:
        return text
    kept: list[str] = []
    for block in _split_blocks(text):
        block_norm = _normalize_text(block)
        if not block_norm:
            continue
        if block_norm == ref_norm:
            continue
        if len(ref_norm) >= 40 and ref_norm in block_norm and len(block_norm) <= len(ref_norm) + 40:
            continue
        kept.append(block)
    return "\n\n".join(kept).strip() if kept else text.strip()


def _preclean_html(raw_html: str) -> str:
    """Remove noise tags and noise-marker nodes from HTML."""
    if not raw_html:
        return ""
    try:
        from bs4 import BeautifulSoup
    except Exception as exc:
        logger.debug("BeautifulSoup unavailable during preclean, returning raw HTML: %s", exc)
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


def _split_trafilatura_sections(text: str) -> str:
    """Re-split over-merged trafilatura output when possible."""
    if not text or "\n\n" in text:
        return text
    parts = re.split(r"\n(?=\d+\.\s)", text)
    if len(parts) > 1:
        return "\n\n".join(p.strip() for p in parts if p.strip())
    return text


def _flat_nav_structural_ratio(text: str) -> float:
    """Structural flat-text nav heuristic (no keyword dictionary).

    Signals: high short-line ratio, high pipe/separator density, low sentence
    density.  These are language-independent and reasonably accurate for
    detecting flattened menu dumps in trafilatura output.
    """
    if not text or len(text) < 40:
        return 0.0
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return 0.0

    short_line_ratio = sum(1 for l in lines if len(l.split()) <= 4) / len(lines)
    seps = len(re.findall(r"[|›»·•]", text))
    sep_density = min(seps / max(len(text), 1) * 15, 1.0)

    parts = re.split(r"[.!?;:。！？]+", text)
    parts = [p.strip() for p in parts if p.strip()]
    sentence_ratio = (
        sum(1 for p in parts if 8 <= len(p.split()) <= 90) / len(parts)
        if parts else 0.0
    )

    score = (
        0.55 * short_line_ratio
        + 0.30 * sep_density
        - 0.35 * sentence_ratio
    )
    return max(0.0, min(score, 1.0))


def _choose_extraction(
    cleaned_html: str,
    *,
    url: str = "",
    min_clean_chars: int = 220,
) -> tuple[str, str, dict[str, int | str]]:
    """Pick trafilatura or DOM blocks, whichever yields cleaner structure."""
    dom_stats: dict[str, int | str] = {}
    traf = _extract_text_with_trafilatura(cleaned_html)
    traf = _split_trafilatura_sections(traf)
    dom_text, dom_stats = _extract_text_with_dom_blocks(cleaned_html, url=url)

    traf_n = len(_normalize_text(traf))
    dom_n = len(_normalize_text(dom_text))
    traf_paras = len(_split_blocks(traf))
    dom_paras = len(_split_blocks(dom_text)) if dom_text else 0

    traf_has_table = "|" in traf and traf.count("\n") >= 4
    traf_nav_heavy = _flat_nav_structural_ratio(traf) > 0.18
    total_dom_cand = int(dom_stats.get("total_candidates", 0))
    dom_nav_rej = int(dom_stats.get("nav_rejected", 0))
    dom_cleaned_heavily = (
        total_dom_cand > 0 and dom_nav_rej / total_dom_cand >= 0.35 and dom_paras >= 1
    )

    prefer_dom = False
    if dom_stats.get("extraction_status") == "nav_heavy":
        prefer_dom = dom_n > traf_n
    elif dom_cleaned_heavily:
        prefer_dom = True
    elif traf_has_table and not traf_nav_heavy and traf_n >= min_clean_chars:
        prefer_dom = False
    elif dom_n >= min_clean_chars:
        if traf_n < min_clean_chars:
            prefer_dom = True
        elif traf_paras <= 1 and dom_paras >= 2:
            prefer_dom = True
        elif dom_paras >= traf_paras + 2:
            prefer_dom = True
        elif traf_nav_heavy:
            prefer_dom = True

    structural_min = min(200, min_clean_chars)

    if prefer_dom and dom_n >= structural_min:
        return dom_text, "dom_blocks", dom_stats
    if dom_cleaned_heavily and dom_n >= structural_min:
        return dom_text, "dom_blocks", dom_stats
    if traf_n >= min_clean_chars:
        return traf, "trafilatura", dom_stats
    if dom_n >= min_clean_chars:
        return dom_text, "dom_blocks", dom_stats
    if dom_cleaned_heavily and dom_n > 0:
        return dom_text, "dom_blocks", dom_stats
    if traf_n > dom_n:
        return traf, "trafilatura", dom_stats
    return dom_text or traf, "dom_blocks" if dom_text else "trafilatura", dom_stats


def _extract_text_with_dom_blocks(
    cleaned_html: str,
    *,
    url: str = "",
) -> tuple[str, dict[str, int | str]]:
    """DOM-aware block extraction (replaces naïve bs4 fallback)."""
    from core.extract.dom_block_extractor import extract_dom_blocks

    blocks, stats = extract_dom_blocks(cleaned_html, url=url)
    if stats.get("extraction_status") == "nav_heavy":
        return "", stats
    if not blocks:
        return "", stats
    return "\n\n".join(blocks), stats


def _extract_text_with_bs4(cleaned_html: str) -> str:
    if not cleaned_html:
        return ""
    try:
        from bs4 import BeautifulSoup
    except Exception as exc:
        logger.debug("trafilatura unavailable, skipping extraction: %s", exc)
        return ""

    soup = BeautifulSoup(cleaned_html, "html.parser")
    blocks: list[str] = []
    for node in soup.find_all(_BLOCK_TAGS):
        if node.name not in _LEAF_BLOCK_TAGS and node.find(_LEAF_BLOCK_TAGS):
            continue
        text = _normalize_text(node.get_text(separator=" ", strip=True))
        if len(text) >= 40:
            blocks.append(text)
    if not blocks:
        return soup.get_text(separator="\n", strip=True) or ""
    return "\n\n".join(blocks)


def _get_boilerplate_filter():
    """Return a callable that returns True for boilerplate text blocks."""
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


def _split_blocks(text: str) -> list[str]:
    pieces = re.split(r"\n\s*\n|(?<=\.)\s{2,}", text or "")
    return [n for p in pieces if (n := _normalize_text(p))]


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------

def _extract_text_with_trafilatura(cleaned_html: str) -> str:
    if not cleaned_html:
        return ""
    try:
        import trafilatura
    except Exception as exc:
        logger.debug("trafilatura.extract failed: %s", exc)
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
    score += min(chars / 1_200.0, 1.0) * 0.50
    score += min(block_count / 6.0, 1.0) * 0.20
    score += max(0.0, min(alpha_ratio, 1.0)) * 0.25
    score -= min(digit_ratio, 0.20) * 0.20
    score -= min(marker_penalty * 0.08, 0.25)
    return max(0.0, min(round(score, 4), 1.0))


# ---------------------------------------------------------------------------
# Semantic extraction (optional)
# ---------------------------------------------------------------------------

def _semantic_extract(text: str, query: str, settings: dict[str, Any]) -> tuple[str, float]:
    if settings.get("mode") != "semantic" or not query.strip():
        return text, 0.0
    try:
        from core.extract.semantic import ensure_embedder_ready, extract_relevant_content
    except ImportError:
        return text, 0.0

    semantic_input = text[: max(0, int(settings.get("input_char_limit", 15_000)))]
    if not semantic_input:
        return text, 0.0
    try:
        ensure_embedder_ready(require_cuda=bool(settings.get("semantic_require_cuda", False)))
        preview_text, scored_chunks = extract_relevant_content(
            text=semantic_input,
            query=query,
            max_chars=max(200, int(settings.get("output_chars", 1_400)) * 2),
            top_k=max(1, int(settings.get("top_k", 3))),
            min_score=float(settings.get("semantic_min_score", 0.20)),
        )
    except Exception as exc:
        logger.debug("Semantic extract failed, using lexical text only: %s", exc)
        return text, 0.0

    scores = [float(score) for _, score in (scored_chunks or []) if isinstance(score, (int, float))]
    semantic_score = max(scores) if scores else 0.0
    return preview_text or text, max(0.0, min(round(semantic_score, 4), 1.0))


# ---------------------------------------------------------------------------
# build_preview_payload (main entry point for content_processor)
# ---------------------------------------------------------------------------

def warm_preview_models(settings: Optional[dict[str, Any]] = None) -> None:
    """Pre-warm embedding models if semantic mode is active."""
    active = dict(settings or get_preview_settings())
    if active.get("mode") == "semantic":
        try:
            from core.extract.semantic import ensure_embedder_ready
            ensure_embedder_ready(require_cuda=bool(active.get("semantic_require_cuda")))
        except Exception as exc:
            logger.debug("Preview model warmup failed: %s", exc)
            pass


def build_preview_payload(
    url: str,
    raw_html: str,
    query: str = "",
    domain_info: Optional[Any] = None,
    settings: Optional[dict[str, Any]] = None,
) -> PreviewPayload:
    """Extract a relevance-scored, query-focused preview from raw HTML."""
    from core.extract.profile_chunk_selector import (
        compress_chunks_profiled,
        policy_family,
        resolve_chunk_policy,
    )

    active_settings = dict(settings or get_preview_settings())
    query_type = str(active_settings.get("query_type") or "general")
    fam = policy_family(query_type)
    policy = resolve_chunk_policy(
        query_type,
        char_budget=int(active_settings.get("output_chars", 1_400)),
    )
    active_settings["output_chars"] = policy.char_budget

    seo_reference, seo_reference_source = _resolve_serp_reference(active_settings, raw_html)
    if seo_reference:
        active_settings["seo_reference"] = seo_reference
        active_settings["seo_reference_source"] = seo_reference_source

    working_html = raw_html
    _did_use_gliner = False
    strategy_parts: list[str] = []
    if seo_reference_source == "serp_snippet" and seo_reference:
        working_html = _inject_serp_reference_into_html(raw_html, seo_reference)
        strategy_parts.append("serp_inject")
    elif seo_reference_source == "page_title":
        strategy_parts.append("title_ref")

    cleaned_html = _preclean_html(working_html)
    nav_rejected = 0
    extraction_status = "ok"
    chunks_selected = 0
    seo_rejected = 0

    min_clean = int(active_settings.get("min_clean_chars", 220))
    extracted, extract_method, dom_stats = _choose_extraction(
        cleaned_html, url=url, min_clean_chars=min_clean,
    )
    if extract_method:
        strategy_parts.append(extract_method)
    nav_rejected = int(dom_stats.get("nav_rejected", 0))
    extraction_status = str(dom_stats.get("extraction_status", "ok"))
    if extraction_status == "nav_heavy" and not extracted.strip():
        strategy_parts.append("nav_gate")

    dom_had_cleanup = nav_rejected >= 3 and extract_method == "dom_blocks"
    if len(_normalize_text(extracted)) < min_clean and not dom_had_cleanup:
        bs4_text = _extract_text_with_bs4(cleaned_html)
        if len(_normalize_text(bs4_text)) > len(_normalize_text(extracted)):
            extracted = bs4_text
            strategy_parts.append("bs4_last_resort")

    if len(_normalize_text(extracted)) < min_clean and not dom_had_cleanup:
        regex_text = _regex_html_to_text(cleaned_html or raw_html)
        if len(regex_text) > len(_normalize_text(extracted)):
            extracted = regex_text
            strategy_parts.append("regex")

    cleaned_text, block_count = _clean_extracted_text(extracted)
    if seo_reference:
        cleaned_text = _strip_serp_reference_blocks(cleaned_text, seo_reference)
        if (
            query.strip()
            and cleaned_text.strip()
            and seo_reference_source in {"serp_snippet", "serp_title"}
        ):
            from core.extract.micro_chunk_worker import prune_micro_chunks

            cleaned_text, micro_dbg = prune_micro_chunks(
                cleaned_text,
                query,
                reference_text=seo_reference,
            )
            if micro_dbg.clauses_dropped or micro_dbg.sentences_dropped:
                strategy_parts.append("micro_prune")

    quality_score = _estimate_quality(cleaned_text, block_count)
    if extraction_status == "nav_heavy":
        quality_score = min(quality_score, 0.15)

    output_chars = max(120, int(active_settings.get("output_chars", policy.char_budget)))

    compress_debug: dict[str, object] = {}
    if query.strip() and cleaned_text:
        compressed, compress_debug = compress_chunks_profiled(
            cleaned_text,
            query,
            query_type=query_type,
            char_budget=output_chars,
        )
        if compressed.strip():
            strategy_parts.append("profiled")
            cleaned_text = compressed
            chunks_selected = int(compress_debug.get("chunks_selected", 0))
            seo_rejected = int(compress_debug.get("rejected_seo", 0))

    _depth_types = frozenset({"technical", "academic", "medical", "troubleshooting"})
    if (
        active_settings.get("enable_gliner", False)
        and query.strip()
        and cleaned_text
        and query_type in _depth_types
    ):
        try:
            from core.config.hardware import get_hardware_profile
            hw = get_hardware_profile()
        except Exception:
            hw = "cpu_safe"
        run_gliner, gliner_device = _should_run_gliner(quality_score, hw)
        if run_gliner:
            paragraphs_for_gliner = _split_blocks(cleaned_text)
            query_terms_for_gliner = _bm25_tokenize(query)
            gliner_budget = output_chars * 2 if active_settings.get("mode") == "semantic" else output_chars
            gliner_text, used_gliner = _gliner_compress(
                paragraphs_for_gliner,
                query_terms_for_gliner,
                gliner_budget,
                device=gliner_device,
                query_type=query_type,
            )
            if gliner_text.strip() and used_gliner:
                cleaned_text = gliner_text
                _did_use_gliner = True
                strategy_parts.append(f"gliner_{gliner_device[:3]}")

    preview_text, semantic_score = _semantic_extract(cleaned_text, query, active_settings)
    if preview_text != cleaned_text and preview_text.strip():
        strategy_parts.append("semantic")

    if not preview_text.strip():
        preview_text = cleaned_text

    compact_preview = preview_text.strip()
    if "\n\n" not in compact_preview and " | " in compact_preview:
        compact_preview = compact_preview.replace(" | ", "\n\n")
    compact_preview = _truncate_at_sentence(compact_preview, output_chars)

    if _has_latex(compact_preview):
        compact_preview = _render_latex_for_llm(compact_preview)
        strategy_parts.append("latex")

    if not compact_preview.strip() and extraction_status == "nav_heavy":
        extraction_status = "nav_heavy_empty"

    if not compact_preview.strip() and seo_reference:
        compact_preview = _truncate_at_sentence(seo_reference, output_chars)
        strategy_parts.append("ref_fallback")

    return PreviewPayload(
        text=compact_preview,
        semantic_score=max(0.0, min(float(semantic_score or 0.0), 1.0)),
        quality_score=max(0.0, min(float(quality_score or 0.0), 1.0)),
        clean_chars=len(_normalize_text(cleaned_text)),
        used_gliner=_did_use_gliner,
        strategy_used="+".join(strategy_parts) if strategy_parts else "empty",
        extraction_status=extraction_status,
        policy_family=fam,
        chunks_selected=chunks_selected,
        seo_rejected=seo_rejected,
        nav_rejected=nav_rejected,
    )
