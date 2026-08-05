# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import pytest

from core.fetch.shopping.parse import parse_amount_value, parse_price


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "amount", "currency"),
    [
        ("5,58$", 5.58, "USD"),
        ("5.58$", 5.58, "USD"),
        ("5, 58$", 5.58, "USD"),
        ("$5.58", 5.58, "USD"),
        ("$5,58", 5.58, "USD"),
        ("$5, 58", 5.58, "USD"),
        ("$ 5, 58", 5.58, "USD"),
        ("1,234.56$", 1234.56, "USD"),
        ("1.234,56€", 1234.56, "EUR"),
        ("1 234,56 €", 1234.56, "EUR"),
        ("22 999 грн", 22999.0, "UAH"),
        ("₴ 22 999", 22999.0, "UAH"),
        ("od6,99zł", 6.99, "PLN"),
        ("1 299 zł", 1299.0, "PLN"),
        ("RTX 5070 £518.99", 518.99, "GBP"),
        ("£518.99 RTX 5070", 518.99, "GBP"),
        ("from $5.58", 5.58, "USD"),
        ("₽ 12 345", 12345.0, "RUB"),
        ("12 345 руб", 12345.0, "RUB"),
        ("¥12 345", 12345.0, "JPY"),
        ("12 345 円", 12345.0, "JPY"),
    ],
)
def test_parse_price_accepts_common_precise_formats(text: str, amount: float, currency: str) -> None:
    price_text, price_value, parsed_currency = parse_price(text)

    assert price_text
    assert price_value == pytest.approx(amount)
    assert parsed_currency == currency


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "amount"),
    [
        ("5", 5.0),
        ("5.5", 5.5),
        ("5,5", 5.5),
        ("5.58", 5.58),
        ("5,58", 5.58),
        ("5, 58", 5.58),
        ("1 234", 1234.0),
        ("12 345", 12345.0),
        ("123 456", 123456.0),
        ("1 234 567", 1234567.0),
        ("1,234.56", 1234.56),
        ("1.234,56", 1234.56),
        ("1 234,56", 1234.56),
        ("1 234.56", 1234.56),
        ("1\xa0234,56", 1234.56),
        ("5,999", 5999.0),
        ("5.999", 5999.0),
        ("999999", 999999.0),
    ],
)
def test_parse_amount_value_accepts_precise_number_formats(text: str, amount: float) -> None:
    assert parse_amount_value(text) == pytest.approx(amount)


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "",
        "abc",
        "5 58",
        "12 34 567",
        "1,23,456",
        "1.234.56",
        "1,234,56",
        "5,",
        ".58",
        "5.9999",
        "5,9999",
        "5..58",
        "5,,58",
        "12a34",
    ],
)
def test_parse_amount_value_rejects_ambiguous_or_invalid_numbers(text: str) -> None:
    assert parse_amount_value(text) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "",
        "price unavailable",
        "call for price",
        "5,58",
        "5 58$",
        "5,$58",
        "$",
        "$ abc",
        "RTX 5070",
        "5070 £",
        "GPU 5070 518.99",
        "12 34 567 грн",
        "1,23,456$",
        "1.234.56€",
        "RUB 12 345",
        "USD 12.34",
    ],
)
def test_parse_price_returns_empty_when_format_is_not_a_price(text: str) -> None:
    assert parse_price(text) == ("", None, "")


@pytest.mark.unit
def test_parse_price_does_not_infer_missing_currency() -> None:
    price_text, price_value, currency = parse_price("The product costs 1299 today", default_currency="USD")

    assert price_text == ""
    assert price_value is None
    assert currency == ""


@pytest.mark.unit
def test_parse_price_prefers_marked_html_currency_over_provider_default() -> None:
    price_text, price_value, currency = parse_price("5,58$", default_currency="GBP")

    assert price_text == "5,58$"
    assert price_value == pytest.approx(5.58)
    assert currency == "USD"


@pytest.mark.unit
def test_parse_price_allows_bare_amount_only_for_structured_fields() -> None:
    assert parse_price("1299", default_currency="USD") == ("", None, "")

    price_text, price_value, currency = parse_price("1299", default_currency="USD", allow_bare=True)

    assert price_text == "1299"
    assert price_value == pytest.approx(1299.0)
    assert currency == "USD"


@pytest.mark.unit
def test_parse_price_rejects_rating_as_ruble_price() -> None:
    assert parse_price("Видеокарта RTX 5070 5.0 Рейтинг магазина", default_currency="RUB") == ("", None, "")
