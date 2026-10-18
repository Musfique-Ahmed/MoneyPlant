"""Transaction schemas."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import Currency


class Direction(str, Enum):
    INFLOW = "inflow"
    OUTFLOW = "outflow"


class PaymentStatus(str, Enum):
    PAID = "paid"
    PENDING = "pending"
    PARTIAL = "partial"


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    business_id: str
    tx_date: date
    cash_flow_date: date | None
    description: str
    amount: str
    currency: Currency
    direction: Direction
    category: str
    payment_status: PaymentStatus | None
    customer_or_supplier: str | None
    source_file: str | None
    source_sheet: str | None
    source_row: int | None
    import_job_id: str | None
    created_at: datetime


class TransactionList(BaseModel):
    items: list[TransactionRead]
    total: int


class FinancialSummary(BaseModel):
    """The dashboard's authoritative summary. Computed by the engine, not the LLM."""

    model_config = ConfigDict(extra="forbid")

    business_id: str
    currency: Currency
    period_start: date
    period_end_exclusive: date
    revenue: str
    direct_costs: str
    gross_profit: str
    gross_margin: str | None
    operating_expenses: str
    operating_profit: str
    operating_margin: str | None
    cash_inflows: str
    cash_outflows: str
    net_cash_movement: str
    opening_cash: str
    closing_cash: str
    minimum_projected_cash: str
    cash_runway_months: str | None
    transaction_count: int
    data_coverage: dict[str, bool] = Field(
        default_factory=dict,
        description="Which metric categories have data (revenue, direct_costs, opex, etc.)",
    )
    warnings: list[str] = Field(default_factory=list)
    is_empty: bool = False
