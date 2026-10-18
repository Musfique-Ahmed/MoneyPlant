"""Business request/response schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import Currency


class Industry(str, Enum):
    MANUFACTURING = "manufacturing"
    RETAIL = "retail"
    SERVICE = "service"
    WHOLESALE = "wholesale"
    FOOD = "food"


class BusinessCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    industry: Industry
    currency: Currency = Currency.USD
    fiscal_year_start_month: int = Field(default=1, ge=1, le=12)
    locale: str = Field(default="en-US", max_length=16)
    min_cash_reserve: str = "0"
    target_operating_margin: str = "0.10"
    max_unsold_inventory_exposure_pct: str = "0.20"


class BusinessUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    industry: Industry | None = None
    currency: Currency | None = None
    fiscal_year_start_month: int | None = Field(default=None, ge=1, le=12)
    locale: str | None = None
    min_cash_reserve: str | None = None
    target_operating_margin: str | None = None
    max_unsold_inventory_exposure_pct: str | None = None


class BusinessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    industry: Industry
    currency: Currency
    fiscal_year_start_month: int
    locale: str
    min_cash_reserve: str
    target_operating_margin: str
    max_unsold_inventory_exposure_pct: str
    created_at: datetime
    updated_at: datetime

    def to_decimal(self, field: str) -> Decimal:
        return Decimal(getattr(self, field))
