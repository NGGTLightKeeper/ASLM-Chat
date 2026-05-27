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
) -> tuple[str, bool]:
    """Re-rank paragraphs by BM25 + GLiNER entity-density hybrid, fit to max_chars.

    Returns (compressed_text, used_gliner).
    used_gliner=False means GLiNER was unavailable; caller should fall back.
    Hybrid score: 55 % BM25 relevance + 45 % entity density.
    """
    if not paragraphs:
        return "", False

    try:
        from core.extract.gliner_wrapper import score_entity_density
        gliner_scores = score_entity_density(paragraphs, device=device)
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
    active_settings = dict(settings or get_preview_settings())
    cleaned_html = _preclean_html(raw_html)

    _did_use_gliner = False
    strategy_parts: list[str] = []
    extracted = _extract_text_with_trafilatura(cleaned_html)
    if extracted:
        strategy_parts.append("trafilatura")

    if len(_normalize_text(extracted)) < int(active_settings.get("min_clean_chars", 220)):
        bs4_text = _extract_text_with_bs4(cleaned_html)
        if len(_normalize_text(bs4_text)) > len(_normalize_text(extracted)):
            extracted = bs4_text
            strategy_parts.append("bs4")

    if len(_normalize_text(extracted)) < int(active_settings.get("min_clean_chars", 220)):
        regex_text = _regex_html_to_text(cleaned_html or raw_html)
        if len(regex_text) > len(_normalize_text(extracted)):
            extracted = regex_text
            strategy_parts.append("regex")

    cleaned_text, block_count = _clean_extracted_text(extracted)
    quality_score = _estimate_quality(cleaned_text, block_count)

    output_chars = max(120, int(active_settings.get("output_chars", 1_400)))

    # BM25 compression: always runs before semantic, no GPU required.
    # When semantic is enabled we give it 2x budget so it has room to pick
    # the best chunks; otherwise compress directly to output_chars.
    if query.strip() and cleaned_text:
        bm25_budget = (
            output_chars * 2
            if active_settings.get("mode") == "semantic"
            else output_chars
        )
        compressed = compress_to_budget(cleaned_text, query, bm25_budget)
        if compressed.strip():
            if compressed != cleaned_text:
                strategy_parts.append("bm25")
            cleaned_text = compressed

    # GLiNER densification: hybrid BM25 + entity-density re-ranking.
    # Runs after BM25 pre-selection, before semantic, on paragraphs that fit
    # within 2x output budget. Skipped when enable_gliner=False or conditions
    # (hardware profile + quality score) are not met.
    if active_settings.get("enable_gliner", False) and query.strip() and cleaned_text:
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
                paragraphs_for_gliner, query_terms_for_gliner, gliner_budget, device=gliner_device
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

    compact_preview = _single_line(preview_text)
    compact_preview = _truncate_at_sentence(compact_preview, output_chars)

    # Transpile any remaining LaTeX spans to human-readable notation.
    # Runs after truncation so we don't waste CPU on discarded text.
    if _has_latex(compact_preview):
        compact_preview = _render_latex_for_llm(compact_preview)
        strategy_parts.append("latex")

    return PreviewPayload(
        text=compact_preview,
        semantic_score=max(0.0, min(float(semantic_score or 0.0), 1.0)),
        quality_score=max(0.0, min(float(quality_score or 0.0), 1.0)),
        clean_chars=len(_normalize_text(cleaned_text)),
        used_gliner=_did_use_gliner,
        strategy_used="+".join(strategy_parts) if strategy_parts else "empty",
    )
