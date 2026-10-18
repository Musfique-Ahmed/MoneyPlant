"""Reusable Pydantic schemas for monetary values and periods."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class Currency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"
    INR = "INR"
    CAD = "CAD"
    AUD = "AUD"


# Currency precision table. Extend as needed.
CURRENCY_PRECISION: dict[Currency, int] = {
    Currency.USD: 2,
    Currency.EUR: 2,
    Currency.GBP: 2,
    Currency.JPY: 0,
    Currency.INR: 2,
    Currency.CAD: 2,
    Currency.AUD: 2,
}


class Money(BaseModel):
    """A monetary value. Stored as a string to avoid float precision issues; parsed to Decimal for arithmetic."""

    model_config = ConfigDict(extra="forbid")

    amount: Annotated[str, Field(min_length=1, description="Decimal as a string, e.g. '1234.56'")]
    currency: Currency = Currency.USD

    def to_decimal(self) -> Decimal:
        return Decimal(self.amount)

    @classmethod
    def from_decimal(cls, value: Decimal, currency: Currency = Currency.USD) -> "Money":
        return cls(amount=f"{value:.4f}".rstrip("0").rstrip(".") or "0", currency=currency)


class Period(BaseModel):
    """A monthly reporting period, half-open. ``end_exclusive`` is the first instant of the next period."""

    model_config = ConfigDict(extra="forbid")

    start: date
    end_exclusive: date

    @property
    def label(self) -> str:
        return f"{self.start.isoformat()}"


__all__ = ["Currency", "CURRENCY_PRECISION", "Money", "Period"]
