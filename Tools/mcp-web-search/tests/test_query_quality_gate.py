import asyncio
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config.settings import QueryQualitySection
from services.web_search import (
    _apply_query_quality_effort_policy,
    run_web_search_rich,
    validate_search_query,
)


@pytest.mark.parametrize(
    "query",
    [
        "bästa noise cancelling headphones",
        "лучший python web framework",
        "nejlepší python profiler",
        "cel mai bun router wifi",
        "terbaik laptop gaming",
        "tốt nhất framework web",
        "ベスト Python ORM",
        "เครื่องฟอกอากาศดีที่สุด",
    ],
)
def test_multilingual_seo_queries_are_rejected(query: str) -> None:
    rejection = validate_search_query(query)

    assert rejection is not None
    assert rejection.startswith("BAD_QUERY:")


def test_focused_non_seo_query_passes() -> None:
    assert validate_search_query("asyncio TaskGroup cancellation semantics Python 3.12") is None


@pytest.mark.parametrize(
    "query",
    [
        "Python ORM review",
        "роутер wifi обзор",
        "рейтинг университетов 2026",
        "PostgreSQL vs SQLite comparison",
        "大学 ランキング 2026",
        "เครื่องฟอกอากาศ รีวิว",
        "asyncio cancellation site:best.dev",
    ],
)
def test_ordinary_research_intents_are_not_rejected(query: str) -> None:
    assert validate_search_query(query) is None


def test_rejected_rich_search_does_not_use_high_effort_pipeline(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):  # pragma: no cover - should never execute
        raise AssertionError("WebSearchService should not be constructed for rejected queries")

    monkeypatch.setattr("services.web_search.WebSearchService", fail_if_called)

    payload = asyncio.run(run_web_search_rich("Ultimate guide to Python decorators", effort="high"))

    assert payload["ui"]["status"] == "rejected"
    assert payload["sources"] == []
    assert str(payload["model_context"]).startswith("BAD_QUERY:")


def test_filler_low_effort_policy_is_config_gated() -> None:
    disabled = QueryQualitySection(filler_low_effort_enabled=False)
    enabled = QueryQualitySection(filler_low_effort_enabled=True)

    assert _apply_query_quality_effort_policy(
        "Exhaustive analysis of LLM quantization", "high", disabled
    ).effort == "high"
    decision = _apply_query_quality_effort_policy(
        "Exhaustive analysis of LLM quantization", "high", enabled
    )
    assert decision.effort == "low"
    assert decision.original_effort == "high"
    assert decision.filler_hits == ("exhaustive",)


def test_filler_low_effort_policy_respects_exempt_phrases() -> None:
    enabled = QueryQualitySection(filler_low_effort_enabled=True)

    decision = _apply_query_quality_effort_policy("exhaustive search algorithm", "high", enabled)

    assert decision.effort == "high"
    assert decision.filler_hits == ()


@pytest.mark.parametrize(
    ("query", "expected_hit"),
    [
        ("Beste PostgreSQL Konfiguration", "beste"),
        ("meilleure configuration PostgreSQL", "meilleure"),
        ("configuración perfecta PostgreSQL", "perfecta"),
        ("najlepsza konfiguracja PostgreSQL", "najlepsza"),
        ("أفضل إعدادات PostgreSQL", "أفضل"),
        ("最佳 PostgreSQL 配置", "最佳"),
        ("最高 PostgreSQL 設定", "最高"),
        ("최고 PostgreSQL 설정", "최고"),
        ("terbaik konfigurasi PostgreSQL", "terbaik"),
        ("การตั้งค่า PostgreSQL ที่ดีที่สุด", "ดีที่สุด"),
    ],
)
def test_filler_low_effort_policy_is_multilingual(query: str, expected_hit: str) -> None:
    enabled = QueryQualitySection(filler_low_effort_enabled=True)

    decision = _apply_query_quality_effort_policy(query, "high", enabled)

    assert decision.effort == "low"
    assert expected_hit in decision.filler_hits
