import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.web_search import validate_search_query


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
