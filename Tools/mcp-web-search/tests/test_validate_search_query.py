# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import pytest

from services.web_search import validate_search_query


# validate_search_query — accept concise technical queries.

@pytest.mark.unit
def test_validate_search_query_accepts_concise_technical_query() -> None:
    assert validate_search_query("c++ vector erase complexity") is None


# validate_search_query — reject SEO spam keyword stuffing.

@pytest.mark.unit
def test_validate_search_query_rejects_seo_spam_keywords() -> None:
    rejection = validate_search_query("best ultimate comprehensive complete guide amazing")
    assert rejection is not None
    assert rejection.startswith("BAD_QUERY:")


# validate_search_query — reject queries with too many content tokens.

@pytest.mark.unit
def test_validate_search_query_rejects_too_many_content_tokens() -> None:
    rejection = validate_search_query(
        "one two three four five six seven eight nine ten "
        "eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen"
    )
    assert rejection is not None
    assert "content words" in rejection


# validate_search_query — site: operator must not count as spam.

@pytest.mark.unit
def test_validate_search_query_allows_site_operator_without_counting_as_spam() -> None:
    assert validate_search_query("site:github.com pytorch install cuda") is None


# validate_search_query — empty/whitespace deferred to caller.

@pytest.mark.unit
def test_validate_search_query_empty_is_deferred() -> None:
    assert validate_search_query("") is None
    assert validate_search_query("   ") is None
