"""Pydantic schemas for the cash-flow alerts endpoint.

These mirror ``app.engine.alerts``. Every monetary value is a string
(``decimal.Decimal`` is the engine's source of truth; we don't pretend
floats are safe).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import Currency


class AlertConfigRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low_buffer_months: str
    short_runway_warning_months: str
    short_runway_critical_months: str
    sharp_drop_pct: str


class AlertRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="Stable identifier, e.g. NEGATIVE_CASH, LOW_BUFFER, SHORT_RUNWAY.")
    severity: str = Field(description="Critical | Warning | Info. Text label, not colour.")
    month: int | None = Field(
        default=None,
        description="Month index where the alert applies (1-based). None for whole-period alerts.",
    )
    message: str
    evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="Numbers used to decide the alert. Currency is included as `currency`.",
    )


class MonthlyCashPointRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month_index: int
    opening_cash: str
    net_cash_movement: str
    closing_cash: str


class AlertsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_id: str
    currency: Currency
    horizon_months: int = Field(description="Number of months in the projection window.")
    runway_months: str | None = Field(
        description="Closing cash / avg monthly outflow, or null when outflows are zero.",
    )
    operating_profit: str
    monthly_cash: list[MonthlyCashPointRead] = Field(
        default_factory=list,
        description="Per-month trajectory used to compute the alerts.",
    )
    config: AlertConfigRead
    alerts: list[AlertRead] = Field(
        default_factory=list,
        description="Deterministic alerts derived from the cash series. May be empty.",
    )
    source: str = Field(
        default="transactions-derived",
        description="How the series was built. 'transactions-derived' for raw imports; 'scenario-derived' when sourced from a saved scenario.",
    )
    note: str = Field(
        default=(
            "Alerts are computed deterministically from the imported transactions "
            "by the engine. The LLM and Laya do not participate in this calculation."
        ),
    )


__all__ = ["AlertRead", "AlertConfigRead", "MonthlyCashPointRead", "AlertsResponse"]