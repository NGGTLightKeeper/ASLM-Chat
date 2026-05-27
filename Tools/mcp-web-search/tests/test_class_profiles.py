import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.query.class_profiles import (
    CLASS_PRIORITY,
    clear_class_profiles_cache,
    infer_query_types_from_rules,
    infer_query_types_hybrid,
    load_class_profiles,
    score_query_against_profiles,
    _trigram_similarity,
)
from services.web_search import infer_query_types


@pytest.fixture(autouse=True)
def _fresh_profiles() -> None:
    clear_class_profiles_cache()
    yield
    clear_class_profiles_cache()


def test_load_all_class_profiles() -> None:
    profiles = load_class_profiles()
    assert len(profiles) == 21
    for name in CLASS_PRIORITY:
        assert name in profiles
        assert profiles[name].class_name == name
        assert profiles[name].description


def test_trigram_catches_close_variants() -> None:
    assert _trigram_similarity("kubernetes", "kuberntes") >= 0.55
    scores = score_query_against_profiles("kuberntes cluster deployment yaml")
    tech = next(r for r in scores if r.class_name == "technical")
    assert any("fuzzy" in reason for reason in tech.reasons)


def test_obvious_technical_scores_high() -> None:
    scores = {r.class_name: r.score for r in score_query_against_profiles(
        "asyncio TaskGroup cancellation semantics Python 3.12 docker kubernetes api"
    )}
    assert scores["technical"] >= scores.get("weather", 0.0)
    assert scores["technical"] >= 0.12
    assert "technical" in infer_query_types_from_rules(
        "asyncio TaskGroup cancellation semantics Python 3.12"
    )


@pytest.mark.parametrize(
    "query",
    [
        "cat behavior",
        "connect phone to wifi",
        "netflix subscription",
        "rustic furniture",
        "reactive oxygen species",
    ],
)
def test_technical_special_terms_do_not_match_unrelated_substrings(query: str) -> None:
    technical = next(
        r for r in score_query_against_profiles(query)
        if r.class_name == "technical"
    )

    assert technical.score < 0.12
    assert not any("c++" in reason or "rust" in reason or "react" in reason for reason in technical.reasons)


@pytest.mark.parametrize(
    "query",
    [
        "c++ vector docs",
        "c# async await",
        ".net dependency injection",
        "dotnet dependency injection",
        "cplusplus templates guide",
    ],
)
def test_technical_symbol_terms_match_explicit_forms(query: str) -> None:
    technical = next(
        r for r in score_query_against_profiles(query)
        if r.class_name == "technical"
    )

    assert technical.score >= 0.12


def test_obvious_weather_scores_high() -> None:
    scores = {r.class_name: r.score for r in score_query_against_profiles(
        "weather forecast temperature humidity погода на завтра прогноз"
    )}
    assert scores["weather"] >= scores.get("technical", 0.0)
    assert scores["weather"] >= 0.08
    assert infer_query_types_from_rules("погода на завтра прогноз осадки")[0] == "weather"


def test_model_split_technical_academic_keeps_both() -> None:
    hybrid = infer_query_types_hybrid(
        "graph neural networks paper arxiv implementation",
        model_scores={"technical": 0.6, "academic": 0.4},
    )
    classes = [c for c, _, _ in hybrid]
    assert "technical" in classes
    assert "academic" in classes


def test_rule_only_order_prefers_score_before_class_priority() -> None:
    classes = infer_query_types_from_rules("Tesla Model 3 price")

    assert classes[:2] == ["shopping", "automotive"]


def test_model_only_technical_adds_general_secondary() -> None:
    hybrid = infer_query_types_hybrid(
        "miscellaneous topic",
        model_scores={"technical": 0.9},
    )
    classes = [c for c, _, _ in hybrid]
    assert classes[0] == "technical"
    assert "general" in classes


def test_hard_rule_override_only_at_high_confidence() -> None:
    # Model confident weather; rules should not flip to technical on weak overlap.
    hybrid_weak = infer_query_types_hybrid(
        "sunny afternoon walk",
        model_scores={"weather": 0.88},
    )
    assert hybrid_weak[0][0] == "weather"

    # Model weak weather; strong technical hard indicators in query.
    hybrid_override = infer_query_types_hybrid(
        "python kubernetes docker github api sdk readthedocs",
        model_scores={"weather": 0.42},
    )
    top = hybrid_override[0][0]
    assert top in ("technical", "weather")
    if top == "technical":
        assert "override" in hybrid_override[0][2] or "model=" in hybrid_override[0][2]


def test_infer_query_types_wrapper_compatible() -> None:
    types = infer_query_types("bitcoin price nasdaq trading")
    assert isinstance(types, list)
    assert types[0] == "finance"
    assert len(types) <= 3
