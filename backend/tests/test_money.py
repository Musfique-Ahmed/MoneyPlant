"""Tests for the money primitives: Decimal arithmetic, currency rounding, edge cases."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.finance.money import (
    CurrencyMismatch,
    PRECISION,
    ZERO,
    add,
    div,
    format_money,
    format_quantized,
    mul,
    parse_money_str,
    quantize,
    safe_div_str,
    same_currency,
    sub,
    to_decimal,
)


def test_to_decimal_accepts_common_types() -> None:
    assert to_decimal(1) == Decimal("1")
    assert to_decimal("12.34") == Decimal("12.34")
    assert to_decimal(Decimal("5.6")) == Decimal("5.6")
    # float goes through str to avoid binary float artifacts
    assert to_decimal(0.1) == Decimal("0.1")
    with pytest.raises(TypeError):
        to_decimal(object())  # type: ignore[arg-type]


def test_quantize_uses_currency_precision() -> None:
    assert quantize(Decimal("1.235"), "USD") == Decimal("1.24")  # HALF_UP
    assert quantize(Decimal("1.245"), "USD") == Decimal("1.25")
    assert quantize(Decimal("1.5"), "JPY") == Decimal("2")  # JPY has 0 fractional digits
    assert quantize(Decimal("1.4"), "JPY") == Decimal("1")


def test_quantize_handles_unknown_currency_as_two_dp() -> None:
    # Unknown currencies fall back to 2dp; we never throw on serialization.
    assert quantize(Decimal("1.005"), "XYZ") == Decimal("1.01")


def test_same_currency_case_insensitive() -> None:
    same_currency("usd", "USD")  # should not raise
    with pytest.raises(CurrencyMismatch):
        same_currency("USD", "EUR")


def test_add_sub_round_trip() -> None:
    a = Decimal("100.10")
    b = Decimal("0.20")
    assert add(a, b, "USD") == Decimal("100.30")
    assert sub(add(a, b, "USD"), b, "USD") == a


def test_mul_div_preserve_sign() -> None:
    assert mul(Decimal("2.5"), Decimal("4.0"), "USD") == Decimal("10.00")
    assert div(Decimal("10.00"), Decimal("4.0"), "USD") == Decimal("2.50")
    assert div(Decimal("1"), Decimal("3"), "USD") == Decimal("0.33")  # 0.333... rounded HALF_UP to 0.33


def test_div_by_zero_returns_zero() -> None:
    # Div by zero returns ZERO — never raises. The decision engine treats 0 as "not applicable".
    assert div(Decimal("10"), Decimal("0"), "USD") == ZERO


def test_safe_div_str_returns_none_for_zero_denom() -> None:
    assert safe_div_str(Decimal("10"), Decimal("0"), "USD") is None
    assert safe_div_str(Decimal("10"), Decimal("4"), "USD") == "2.50"
    # places override
    assert safe_div_str(Decimal("1"), Decimal("3"), "USD", places=4) == "0.3333"


def test_format_money_normalises_zero() -> None:
    # "0" is canonical, "-0" never appears.
    assert format_money(Decimal("0"), "USD") == "0.00"
    assert format_money(Decimal("-0.00"), "USD") == "0.00"
    assert format_money(Decimal("1234.5"), "USD") == "1234.50"


def test_format_money_jpy_no_decimals() -> None:
    assert format_money(Decimal("1234"), "JPY") == "1234"
    assert format_money(Decimal("1234.7"), "JPY") == "1235"


def test_parse_money_str_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_money_str("not a number", "USD")
    assert parse_money_str("0.005", "USD") == Decimal("0.01")  # rounded to currency precision


def test_precision_table_contains_major_currencies() -> None:
    for c in ("USD", "EUR", "GBP", "INR", "CAD", "AUD"):
        assert c in PRECISION
        assert PRECISION[c] == 2
    assert PRECISION["JPY"] == 0


def test_format_quantized_preserves_already_quantized_input() -> None:
    # format_quantized is idempotent at the right precision.
    assert format_quantized(Decimal("1.00"), "USD") == "1.00"
    assert format_quantized(Decimal("1.000"), "USD") == "1.00"  # trailing zeros stripped
