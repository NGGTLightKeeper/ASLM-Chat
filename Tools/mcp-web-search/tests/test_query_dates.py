# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Coverage for the query date/recency parser (core/search/query_dates)."""

from __future__ import annotations

import datetime
from types import SimpleNamespace

from core.search.query_dates import resolve_query_dates, stricter_timelimit

_THIS_YEAR = datetime.date.today().year


def _cfg(mode: str = "timelimit"):
    return SimpleNamespace(
        year_hint_mode=mode, year_hint_current="m", year_hint_prev="y", year_hint_older=None
    )


def test_mode_none_is_noop():
    q = f"openai latest news {_THIS_YEAR}"
    assert resolve_query_dates(q, _cfg("none")) == (q, None)


def test_plain_query_untouched():
    assert resolve_query_dates("python asyncio tutorial", _cfg()) == ("python asyncio tutorial", None)


def test_freshness_plus_current_year_derives_and_strips():
    clean, tl = resolve_query_dates(f"gpt-5 release latest news {_THIS_YEAR}", _cfg())
    assert str(_THIS_YEAR) not in clean        # year stripped
    assert "latest news" in clean
    assert tl == "m"                            # current year → year_hint_current


def test_last_year_freshness_derives_prev():
    _, tl = resolve_query_dates(f"foldable phones current {_THIS_YEAR - 1}", _cfg())
    assert tl == "y"                            # last year → year_hint_prev


def test_comma_trailing_year_is_stripped():
    clean, _ = resolve_query_dates("ai developments, 2023-2024", _cfg())
    assert clean == "ai developments"


def test_topic_year_without_freshness_is_kept():
    # No freshness word, no comma → the year is a topic anchor, left in place.
    clean, tl = resolve_query_dates("rust async 2019", _cfg())
    assert clean == "rust async 2019" and tl is None


def test_historical_anchor_suppresses_timelimit():
    # A freshness word but anchored to an old year → no freshness window applied.
    _, tl = resolve_query_dates("history of computing news 2005", _cfg())
    assert tl is None


def test_explicit_timelimit_wins_when_stricter():
    # Explicit 'd' is tighter than a derived 'm' → keep the stricter one.
    _, tl = resolve_query_dates(f"news latest {_THIS_YEAR}", _cfg(), explicit_timelimit="d")
    assert tl == "d"


def test_stricter_timelimit_helper():
    assert stricter_timelimit("d", "y") == "d"
    assert stricter_timelimit(None, "w") == "w"
    assert stricter_timelimit("m", None) == "m"
    assert stricter_timelimit(None, None) is None


def test_old_entity_year_survives_freshness_word():
    # "2022" is a product version, not a recency tag — it must NOT be stripped just because
    # "latest" is present, or the engine query loses what it's actually about (#1).
    clean, tl = resolve_query_dates("Windows Server 2022 latest CU", _cfg())
    assert "2022" in clean
    assert "latest CU" in clean
    # An old year next to a freshness word is a historical anchor → no freshness timelimit.
    assert tl is None


def test_recent_year_still_stripped_under_freshness_word():
    clean, tl = resolve_query_dates(f"AI agents news {_THIS_YEAR}", _cfg())
    assert str(_THIS_YEAR) not in clean        # current year is a recency tag → stripped
    assert tl == "m"
