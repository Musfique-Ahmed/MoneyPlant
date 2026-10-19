"""Pydantic schemas for the financing-options endpoint.

Mirrors ``app.engine.financing``. Serialises the synthetic catalog
``synthetic: true`` flag and the ``catalog_disclaimer`` so the frontend
cannot forget to label the result.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import Currency


class FinancingProductCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    type: str
    min_amount: str
    max_amount: str
    min_months_operating: int
    min_avg_monthly_revenue: str
    max_term_months: int
    indicative_annual_rate: str
    suitable_use_cases: list[str]
    synthetic: bool


class FinancingCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    products: list[FinancingProductCatalogEntry]
    synthetic: bool = Field(
        default=True,
        description="Always true for this contest build — the catalog is illustrative.",
    )
    disclaimer: str = (
        "SYNTHETIC EXAMPLE DATA. Illustrative products only. Not a credit "
        "decision, not a real lender offer, and not financial advice."
    )


class EligibilityCheckRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    requirement: str
    actual: str


class FinancingMatchRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str
    product_name: str
    product_type: str
    label: str = Field(
        description=(
            "One of: recommended, possible, not_recommended. Text label, not colour."
        )
    )
    fit_reasons: list[str]
    unmet_criteria: list[str]
    checks: list[EligibilityCheckRead]
    indicative_annual_rate: str
    requested_amount: str
    term_months: int
    monthly_repayment: str
    dscr: str = Field(
        description=(
            "Debt-service coverage ratio (operating_profit / monthly_repayment), "
            "4dp. Empty string when undefined."
        )
    )
    synthetic: bool


class NoFinancingNeededRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    minimum_projected_cash: str
    funding_need: str


class FinancingOptionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_id: str
    currency: Currency
    funding_need: str
    minimum_projected_cash: str
    avg_monthly_revenue: str
    monthly_operating_profit: str
    months_operating: int
    catalog: FinancingCatalog
    matches: list[FinancingMatchRead] = Field(default_factory=list)
    no_financing_needed: NoFinancingNeededRead | None = None
    note: str = Field(
        default=(
            "Financing options are matched deterministically against a SYNTHETIC "
            "catalog of illustrative products. The LLM and Laya do not participate "
            "in the matching. Not a credit decision."
        )
    )


__all__ = [
    "FinancingProductCatalogEntry",
    "FinancingCatalog",
    "EligibilityCheckRead",
    "FinancingMatchRead",
    "NoFinancingNeededRead",
    "FinancingOptionsResponse",
]
