# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

_PROFILES_DIR = Path(__file__).resolve().parent / "class_profiles"

_REQUIRED_KEYS = frozenset({"class", "description"})

# Priority when multiple classes match (most specific first).
CLASS_PRIORITY: tuple[str, ...] = (
    "finance",
    "medical",
    "journalistic",
    "academic",
    "shopping",
    "troubleshooting",
    "forum",
    "technical",
    "legal",
    "government",
    "real_estate",
    "automotive",
    "travel",
    "weather",
    "local",
    "careers",
    "education",
    "documentation",
    "entertainment",
    "sports",
    "general",
)

_PRIORITY_INDEX = {name: i for i, name in enumerate(CLASS_PRIORITY)}

_WEIGHT_STRONG = 1.0
_WEIGHT_MEDIUM = 0.6
_WEIGHT_WEAK = 0.3
_WEIGHT_HARD = 1.5
_WEIGHT_PHRASE = 1.2
_PENALTY_NEGATIVE = 0.45

_TRIGRAM_THRESHOLD = 0.55
_FUZZY_TERM_MAX_LEN = 48

# Hybrid routing blend weights.
_MODEL_BLEND = 0.72
_RULE_BLEND = 0.28
_RULE_BOOST_CAP = 0.12
_RULE_PENALTY_CAP = 0.10
_GENERAL_SECONDARY_FLOOR = 0.18
_MODEL_CONFIDENT = 0.72
_MODEL_SPLIT_MIN = 0.22
_OVERRIDE_RULE_MIN = 0.85
_OVERRIDE_MODEL_MAX = 0.45

_TEXT_SIG_RE = re.compile(r"[\W_]+", re.UNICODE)
_SPECIAL_TERM_RE = re.compile(r"[+#.]")
_MIN_FUZZY_TERM_LEN = 4
_TOKEN_BOUNDARY = r"(?<![0-9A-Za-z]){}(?![0-9A-Za-z])"


# Rule-based query class profile loaded from JSON.
@dataclass(slots=True)
class ClassProfile:
    class_name: str
    description: str
    strong_terms: list[str] = field(default_factory=list)
    medium_terms: list[str] = field(default_factory=list)
    weak_terms: list[str] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)
    negative_terms: list[str] = field(default_factory=list)
    domain_hints: list[str] = field(default_factory=list)
    url_path_hints: list[str] = field(default_factory=list)
    intent_verbs: list[str] = field(default_factory=list)
    language_hints: dict[str, list[str]] = field(default_factory=dict)
    trigram_aliases: list[str] = field(default_factory=list)
    hard_indicators: list[str] = field(default_factory=list)
    notes: str = ""


# Per-class rule match score with optional debug reasons.
@dataclass(slots=True)
class ClassRuleScore:
    class_name: str
    score: float
    reasons: list[str] = field(default_factory=list)


# Build ClassProfile from one JSON profile object.
def _profile_from_dict(data: dict[str, Any]) -> ClassProfile:
    missing = _REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(f"Profile missing keys {missing}: {data.get('class', '?')}")
    class_name = str(data["class"]).strip()
    if not class_name:
        raise ValueError("Profile 'class' must be non-empty")
    return ClassProfile(
        class_name=class_name,
        description=str(data.get("description", "")),
        strong_terms=list(data.get("strong_terms") or []),
        medium_terms=list(data.get("medium_terms") or []),
        weak_terms=list(data.get("weak_terms") or []),
        phrases=list(data.get("phrases") or []),
        negative_terms=list(data.get("negative_terms") or []),
        domain_hints=list(data.get("domain_hints") or []),
        url_path_hints=list(data.get("url_path_hints") or []),
        intent_verbs=list(data.get("intent_verbs") or []),
        language_hints=dict(data.get("language_hints") or {}),
        trigram_aliases=list(data.get("trigram_aliases") or []),
        hard_indicators=list(data.get("hard_indicators") or []),
        notes=str(data.get("notes") or ""),
    )


# Validate one profile JSON file before merge into cache.
def _validate_profile_file(path: Path, data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: root must be object")
    _profile_from_dict(data)


# Load all class profile JSON files from class_profiles/ (cached).
@lru_cache(maxsize=1)
def load_class_profiles() -> dict[str, ClassProfile]:
    if not _PROFILES_DIR.is_dir():
        raise FileNotFoundError(f"Class profiles directory not found: {_PROFILES_DIR}")
    profiles: dict[str, ClassProfile] = {}
    for path in sorted(_PROFILES_DIR.glob("*.json")):
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        _validate_profile_file(path, data)
        profile = _profile_from_dict(data)
        if profile.class_name in profiles:
            raise ValueError(f"Duplicate class profile: {profile.class_name}")
        profiles[profile.class_name] = profile
    if not profiles:
        raise ValueError(f"No class profiles in {_PROFILES_DIR}")
    return profiles


# Clear cached class profiles for tests or hot reload.
def clear_class_profiles_cache() -> None:
    load_class_profiles.cache_clear()


# Lowercase and collapse non-alphanumeric runs to spaces.
def _normalize_text(text: str) -> str:
    return _TEXT_SIG_RE.sub(" ", (text or "").lower()).strip()


# Character trigram set for fuzzy term matching.
def _char_trigrams(text: str) -> set[str]:
    normalized = _normalize_text(text)
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    padded = f"  {normalized} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


# Jaccard similarity of character trigram sets.
def _trigram_similarity(a: str, b: str) -> float:
    ta, tb = _char_trigrams(a), _char_trigrams(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


# True when term matches query via token, phrase, or boundary regex.
def _term_in_query(
    term: str, query_norm: str, tokens: set[str], query_raw_lower: str = ""
) -> bool:
    raw_term = (term or "").lower()
    if _SPECIAL_TERM_RE.search(raw_term):
        pattern = _TOKEN_BOUNDARY.format(re.escape(raw_term))
        return bool(re.search(pattern, query_raw_lower or ""))
    term_norm = _normalize_text(term)
    if not term_norm:
        return False
    if " " in term_norm:
        return term_norm in query_norm
    if term_norm in tokens:
        return True
    return False


# Trigram fuzzy match for a single term against normalized query.
def _fuzzy_term_match(term: str, query_norm: str) -> tuple[bool, float]:
    if _SPECIAL_TERM_RE.search(term or ""):
        return False, 0.0
    term_norm = _normalize_text(term)
    if not term_norm or len(term_norm) > _FUZZY_TERM_MAX_LEN:
        return False, 0.0
    if len(term_norm) < _MIN_FUZZY_TERM_LEN:
        return False, 0.0
    if " " in term_norm:
        if abs(len(query_norm) - len(term_norm)) <= max(4, len(term_norm) // 3):
            whole = _trigram_similarity(term_norm, query_norm)
            if whole >= _TRIGRAM_THRESHOLD:
                return True, whole
        return False, 0.0
    # Per-word trigram similarity for single-token terms.
    words = query_norm.split()
    best = 0.0
    for word in words:
        if word.startswith(term_norm) or term_norm.startswith(word):
            continue
        if abs(len(word) - len(term_norm)) > max(3, len(term_norm) // 2):
            continue
        sim = _trigram_similarity(term_norm, word)
        if sim > best:
            best = sim
    if best >= _TRIGRAM_THRESHOLD:
        return True, best
    # Whole-query fuzzy for short aliases.
    if abs(len(query_norm) - len(term_norm)) <= max(4, len(term_norm) // 3):
        whole = _trigram_similarity(term_norm, query_norm)
        if whole >= _TRIGRAM_THRESHOLD:
            return True, whole
    return False, best


# Flatten all language_hints term lists for one profile.
def _collect_language_terms(profile: ClassProfile) -> list[str]:
    out: list[str] = []
    for terms in (profile.language_hints or {}).values():
        out.extend(terms)
    return out


# Score query against all loaded profiles; scores normalized to 0..1.
def score_query_against_profiles(query: str) -> list[ClassRuleScore]:
    profiles = load_class_profiles()
    query_raw_lower = (query or "").lower()
    query_norm = _normalize_text(query)
    tokens = set(query_norm.split()) if query_norm else set()
    results: list[ClassRuleScore] = []

    for class_name in CLASS_PRIORITY:
        profile = profiles.get(class_name)
        if profile is None:
            continue
        raw = 0.0
        reasons: list[str] = []
        hard_hits = 0

        # Add exact or fuzzy term hits to raw score and reasons.
        def _apply_terms(terms: list[str], weight: float, label: str) -> None:
            nonlocal raw, hard_hits
            for term in terms:
                if _term_in_query(term, query_norm, tokens, query_raw_lower):
                    raw += weight
                    reasons.append(f"{label}:exact:{term[:40]}")
                else:
                    if len(_normalize_text(term)) < 4 and not _SPECIAL_TERM_RE.search(term):
                        continue
                    matched, sim = _fuzzy_term_match(term, query_norm)
                    if matched:
                        raw += weight * sim
                        reasons.append(f"{label}:fuzzy:{term[:40]}:{sim:.2f}")

        # Term buckets: strong, medium, weak, phrases, hard, intent, language, aliases.
        _apply_terms(profile.strong_terms, _WEIGHT_STRONG, "strong")
        _apply_terms(profile.medium_terms, _WEIGHT_MEDIUM, "medium")
        _apply_terms(profile.weak_terms, _WEIGHT_WEAK, "weak")
        _apply_terms(profile.phrases, _WEIGHT_PHRASE, "phrase")
        _apply_terms(profile.hard_indicators, _WEIGHT_HARD, "hard")
        _apply_terms(profile.intent_verbs, _WEIGHT_MEDIUM, "intent")
        _apply_terms(_collect_language_terms(profile), _WEIGHT_MEDIUM, "lang")
        _apply_terms(profile.trigram_aliases, _WEIGHT_MEDIUM * 0.9, "alias")

        for neg in profile.negative_terms:
            if _term_in_query(neg, query_norm, tokens, query_raw_lower):
                raw -= _PENALTY_NEGATIVE
                reasons.append(f"negative:{neg[:40]}")

        for hard in profile.hard_indicators:
            if _term_in_query(hard, query_norm, tokens, query_raw_lower):
                hard_hits += 1

        # Normalize raw score to 0..1 using profile-specific denominator.
        profile_span = (
            len(profile.strong_terms) * _WEIGHT_STRONG
            + len(profile.medium_terms) * _WEIGHT_MEDIUM
            + len(profile.weak_terms) * _WEIGHT_WEAK
            + len(profile.phrases) * _WEIGHT_PHRASE
            + max(1, len(profile.hard_indicators)) * _WEIGHT_HARD
        )
        denom = max(2.5, min(12.0, profile_span * 0.2 + 2.0))
        score = min(1.0, max(0.0, raw) / denom)
        if hard_hits and profile.hard_indicators:
            score = min(1.0, score + 0.15 * min(hard_hits, 2))
            reasons.append(f"hard_hits:{hard_hits}")

        results.append(ClassRuleScore(class_name=class_name, score=round(score, 4), reasons=reasons))

    results.sort(key=lambda r: (-r.score, _PRIORITY_INDEX.get(r.class_name, 999)))
    return results


# Map class name to rule score for one query.
def _rule_scores_map(query: str) -> dict[str, float]:
    return {r.class_name: r.score for r in score_query_against_profiles(query)}


# Pick top non-general classes by score and CLASS_PRIORITY order.
def _top_rule_classes(scores: list[ClassRuleScore], limit: int = 3, min_score: float = 0.12) -> list[str]:
    picked = [r for r in scores if r.score >= min_score and r.class_name != "general"]
    if not picked:
        return ["general"]
    ordered = sorted(picked, key=lambda r: (-r.score, _PRIORITY_INDEX.get(r.class_name, 999)))[:limit]
    return [r.class_name for r in ordered]


# Rule-only classification compatible with legacy infer_query_types() ordering.
def infer_query_types_from_rules(query: str, limit: int = 3) -> list[str]:
    scores = score_query_against_profiles(query)
    return _top_rule_classes(scores, limit=limit)


# Normalize model label scores to a probability distribution.
def _normalize_model_scores(model_scores: dict[str, float] | None) -> dict[str, float]:
    if not model_scores:
        return {}
    cleaned = {
        str(k).strip(): float(v)
        for k, v in model_scores.items()
        if str(k).strip() and float(v) >= 0.01
    }
    total = sum(max(0.0, v) for v in cleaned.values())
    if total <= 0:
        return {}
    return {k: max(0.0, v) / total for k, v in cleaned.items()}


# Hybrid router: model_scores primary, rules adjust; returns (class, weight, reason).
def infer_query_types_hybrid(
    query: str,
    model_scores: dict[str, float] | None = None,
) -> list[tuple[str, float, str]]:
    rule_list = score_query_against_profiles(query)
    rule_map = {r.class_name: r.score for r in rule_list}
    rule_by_name = {r.class_name: r for r in rule_list}

    model_norm = _normalize_model_scores(model_scores)

    if not model_norm:
        types = infer_query_types_from_rules(query, limit=3)
        return [
            (t, rule_map.get(t, 0.5 if t == "general" else 0.0), "rules-only")
            for t in types
        ]

    blended: dict[str, float] = {}
    reasons: dict[str, str] = {}

    # Base blend: model weight plus capped rule delta.
    for class_name, model_w in model_norm.items():
        rule_w = rule_map.get(class_name, 0.0)
        delta = max(-_RULE_PENALTY_CAP, min(_RULE_BOOST_CAP, (rule_w - 0.25) * _RULE_BLEND))
        blended[class_name] = max(0.0, model_w * _MODEL_BLEND + rule_w * _RULE_BLEND + delta)
        reasons[class_name] = f"model={model_w:.2f},rule={rule_w:.2f},delta={delta:+.2f}"

    # Soft split: keep secondary model classes above threshold.
    model_sorted = sorted(model_norm.items(), key=lambda x: -x[1])
    if len(model_sorted) >= 2:
        primary, p_w = model_sorted[0]
        secondary, s_w = model_sorted[1]
        if s_w >= _MODEL_SPLIT_MIN and primary != secondary:
            blended[secondary] = max(blended.get(secondary, 0.0), s_w * _MODEL_BLEND)
            reasons[secondary] = reasons.get(secondary, "") + f";soft-split={s_w:.2f}"

    # Confident single-class model → add general secondary.
    if model_sorted:
        top_class, top_w = model_sorted[0]
        second_w = model_sorted[1][1] if len(model_sorted) > 1 else 0.0
        if top_w >= _MODEL_CONFIDENT and second_w < 0.15 and top_class != "general":
            if "general" not in blended:
                blended["general"] = _GENERAL_SECONDARY_FLOOR
                reasons["general"] = f"secondary-fallback;primary={top_class}@{top_w:.2f}"

    # High-confidence rule override when hard indicators fire and model is weak.
    if model_sorted:
        model_top = model_sorted[0][0]
        model_top_w = model_sorted[0][1]
        for r in rule_list:
            if r.class_name == model_top or r.class_name == "general":
                continue
            prof = load_class_profiles().get(r.class_name)
            if not prof or not prof.hard_indicators:
                continue
            has_hard = any(h in " ".join(r.reasons) for h in ("hard:", "hard_hits:"))
            if r.score >= _OVERRIDE_RULE_MIN and model_top_w <= _OVERRIDE_MODEL_MAX and has_hard:
                blended[r.class_name] = max(blended.get(r.class_name, 0.0), r.score)
                reasons[r.class_name] = (
                    f"override:rule={r.score:.2f},model_top={model_top}@{model_top_w:.2f}"
                )

    if not blended:
        return [("general", 1.0, "empty-model-fallback")]

    total = sum(blended.values())
    if total <= 0:
        return [("general", 1.0, "zero-blend-fallback")]

    ranked = sorted(blended.items(), key=lambda x: (-x[1], _PRIORITY_INDEX.get(x[0], 999)))
    out: list[tuple[str, float, str]] = []
    for class_name, weight in ranked[:4]:
        if weight / total < 0.05 and class_name != ranked[0][0]:
            continue
        reason = reasons.get(class_name, "hybrid")
        rr = rule_by_name.get(class_name)
        if rr and rr.reasons:
            reason = f"{reason};{rr.reasons[0]}"
        out.append((class_name, round(weight / total, 4), reason))

    if not out:
        out = [("general", 1.0, "fallback")]
    return out[:3]


# Terms for freshness/intent detection (from journalistic profile).
def journalistic_intent_terms() -> frozenset[str]:
    prof = load_class_profiles().get("journalistic")
    if not prof:
        return frozenset()
    terms = set(prof.strong_terms) | set(prof.medium_terms) | set(prof.phrases)
    for lang_terms in prof.language_hints.values():
        terms.update(lang_terms)
    return frozenset(terms)
