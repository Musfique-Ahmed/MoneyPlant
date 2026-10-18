"""Money primitives: Decimal-backed arithmetic with currency-aware rounding.

The engine never accepts floats. All public helpers take ``Decimal`` or
``str`` and return ``Decimal``. Mixed-currency arithmetic raises
:class:`CurrencyMismatch`.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Final


class CurrencyMismatch(ValueError):
    """Raised when arithmetic is attempted on values with different currencies."""


# Currency precision table — extend as needed.
PRECISION: Final[dict[str, int]] = {
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "JPY": 0,
    "INR": 2,
    "CAD": 2,
    "AUD": 2,
}

ZERO: Final[Decimal] = Decimal("0")


def to_decimal(value: Decimal | str | int | float) -> Decimal:
    """Coerce any common numeric to ``Decimal``. Floats go through ``str`` to avoid float artifacts."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, str)):
        return Decimal(str(value))
    if isinstance(value, float):
        return Decimal(str(value))
    raise TypeError(f"Cannot convert {type(value).__name__} to Decimal")


def quantize(amount: Decimal, currency: str) -> Decimal:
    """Round ``amount`` to the currency's standard precision using ROUND_HALF_UP."""
    prec = PRECISION.get(currency.upper(), 2)
    quantum = Decimal(10) ** -prec
    return amount.quantize(quantum, rounding=ROUND_HALF_UP)


def same_currency(a: str, b: str) -> None:
    if a.upper() != b.upper():
        raise CurrencyMismatch(f"Currency mismatch: {a!r} vs {b!r}")


def add(a: Decimal, b: Decimal, currency: str) -> Decimal:
    return quantize(a + b, currency)


def sub(a: Decimal, b: Decimal, currency: str) -> Decimal:
    return quantize(a - b, currency)


def mul(a: Decimal, b: Decimal, currency: str) -> Decimal:
    return quantize(a * b, currency)


def div(a: Decimal, b: Decimal, currency: str) -> Decimal:
    if b == ZERO:
        return ZERO
    return quantize(a / b, currency)


def safe_div_str(a: Decimal, b: Decimal, currency: str, places: int | None = None) -> str | None:
    """Division that returns ``None`` for zero denominator — the engine's canonical "undefined" path.

    If ``places`` is given, the result is formatted to that many decimal places (e.g. for
    ratios like margin where 4 dp is more useful than currency precision). Otherwise the
    currency's standard precision is used.
    """
    if b == ZERO:
        return None
    q = a / b
    if places is not None:
        q = q.quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)
        return _format_to_places(q, places)
    return format_quantized(q, currency)


def _format_to_places(amount: Decimal, places: int) -> str:
    """Format a Decimal to exactly ``places`` decimal digits, stripping the sign on zero."""
    s = f"{amount:.{places}f}"
    if s.startswith("-") and Decimal(s) == ZERO:
        s = s[1:]
    return s


def format_money(amount: Decimal, currency: str) -> str:
    """Format a Decimal as a string with the currency's precision. Negative numbers are prefixed with '-'."""
    return format_quantized(quantize(amount, currency), currency)


def format_quantized(amount: Decimal, currency: str) -> str:
    """Format a Decimal that's already at the right precision."""
    prec = PRECISION.get(currency.upper(), 2)
    # ``f`` formatting with the right number of decimals
    s = f"{amount:.{prec}f}"
    # Ensure zero is "0.00" not "-0.00"
    if s.startswith("-") and Decimal(s) == ZERO:
        s = s[1:]
    return s


def parse_money_str(value: str | Decimal | int, currency: str) -> Decimal:
    """Parse a money string to a Decimal that's already at the currency's precision."""
    try:
        d = to_decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid money value: {value!r}") from exc
    return quantize(d, currency)


__all__ = [
    "CurrencyMismatch",
    "PRECISION",
    "ZERO",
    "to_decimal",
    "quantize",
    "same_currency",
    "add",
    "sub",
    "mul",
    "div",
    "safe_div_str",
    "format_money",
    "format_quantized",
    "parse_money_str",
]