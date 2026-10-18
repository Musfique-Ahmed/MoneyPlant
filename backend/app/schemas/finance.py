"""Scenario + result schemas. Inputs are union-typed by industry."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.business import Industry
from app.schemas.money import Currency, Money


# --- Manufacturing ---------------------------------------------------------


class ManufacturingInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    industry: Literal[Industry.MANUFACTURING] = Industry.MANUFACTURING
    opening_cash: str
    opening_raw_material_qty: str
    planned_raw_material_purchase_qty: str
    material_unit_cost: str
    material_per_unit: str
    material_waste_pct: str = "0"
    planned_production_qty: str
    production_capacity_qty: str
    labor_cost_per_unit: str
    other_variable_cost_per_unit: str = "0"
    operating_expenses: str = "0"
    selling_price: str
    expected_units_sold: str
    customer_payment_delay_periods: int = Field(default=1, ge=0, le=12)
    supplier_payment_delay_periods: int = Field(default=0, ge=0, le=12)
    horizon_months: int = Field(default=1, ge=1, le=36)
    business_goal: str | None = None


# --- Retail / Wholesale / Food (inventory-based) ---------------------------


class InventoryInputs(BaseModel):
    """Shared inputs for retail, wholesale, and food profiles. Industry tag controls which downstream rules/UI copy are used."""

    model_config = ConfigDict(extra="forbid")

    industry: Literal[Industry.RETAIL, Industry.WHOLESALE, Industry.FOOD]
    opening_cash: str
    opening_inventory_units: str
    planned_purchase_units: str
    purchase_unit_cost: str
    selling_price: str
    expected_units_sold: str
    shrinkage_pct: str = "0"
    operating_expenses: str = "0"
    supplier_payment_delay_periods: int = Field(default=0, ge=0, le=12)
    customer_payment_delay_periods: int = Field(default=0, ge=0, le=12)
    horizon_months: int = Field(default=1, ge=1, le=36)
    business_goal: str | None = None


# --- Service ---------------------------------------------------------------


class ServiceInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    industry: Literal[Industry.SERVICE] = Industry.SERVICE
    opening_cash: str
    billable_hours_capacity: str
    planned_billable_utilization_pct: str
    hourly_price: str
    project_revenue: str | None = None
    labor_cost_per_hour: str
    contractor_cost: str = "0"
    project_expenses: str = "0"
    operating_expenses: str = "0"
    invoice_payment_delay_periods: int = Field(default=1, ge=0, le=12)
    horizon_months: int = Field(default=1, ge=1, le=36)
    business_goal: str | None = None


ScenarioInputs = Annotated[
    Union[ManufacturingInputs, InventoryInputs, ServiceInputs],
    Field(discriminator="industry"),
]


# --- Result ----------------------------------------------------------------


class ScenarioResult(BaseModel):
    """The engine's authoritative output. All numbers as strings; consumers parse to Decimal."""

    model_config = ConfigDict(extra="forbid")

    engine_version: str
    calculation_timestamp: datetime
    currency: Currency

    # Manufacturing / inventory / service all converge on these headline numbers.
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
    contribution_margin: str | None
    units_sold: str | None = None
    units_produced: str | None = None
    unsold_inventory_units: str | None = None
    unsold_inventory_value: str | None = None
    material_shortage: str | None = None
    feasible_production: str | None = None

    warnings: list[str] = Field(default_factory=list)
    invariants_ok: bool = True
    invariants_failures: list[str] = Field(default_factory=list)


class ScenarioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    inputs: dict[str, Any]


class ScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    business_id: str
    name: str
    industry: Industry
    description: str
    status: str
    created_at: datetime
    updated_at: datetime
    latest_version_number: int | None = None
    latest_version_id: str | None = None
    latest_result: ScenarioResult | None = None


class ScenarioCompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_id: str
    scenario_ids: list[str] = Field(min_length=1, max_length=5)


class ScenarioComparisonRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    scenario_name: str
    industry: Industry
    revenue: str
    direct_costs: str
    gross_profit: str
    operating_profit: str
    operating_margin: str | None
    closing_cash: str
    minimum_projected_cash: str
    unsold_inventory_value: str | None
    business_goal: str | None


class ScenarioComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[ScenarioComparisonRow]
    baseline_id: str
    diffs: list[dict[str, str | None]] = Field(
        default_factory=list,
        description="Per-scenario deltas vs baseline. Percentage values are strings; None when the baseline is zero (no NaN/Inf).",
    )
    warnings: list[str] = Field(default_factory=list)


# --- Sensitivity -----------------------------------------------------------


class SensitivityAxis(str, Enum):
    SALES_VOLUME = "sales_volume"
    SELLING_PRICE = "selling_price"
    MATERIAL_COST = "material_cost"
    LABOR_COST = "labor_cost"
    CUSTOMER_PAYMENT_DELAY = "customer_payment_delay"
    SUPPLIER_PAYMENT_DELAY = "supplier_payment_delay"
    WASTE = "waste"
    OPEX = "opex"


class SensitivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_id: str
    inputs: dict[str, Any]
    axes: list[SensitivityAxis] = Field(default_factory=list)
    # Multipliers as strings, e.g. ["-0.25", "-0.10", "0", "0.10", "0.25"]
    multipliers: list[str] = Field(
        default_factory=lambda: ["-0.25", "-0.10", "0", "0.10", "0.25"]
    )


class SensitivityPoint(BaseModel):
    multiplier: str
    revenue: str
    operating_profit: str
    closing_cash: str
    minimum_projected_cash: str


class SensitivitySeries(BaseModel):
    axis: SensitivityAxis
    points: list[SensitivityPoint]


class SensitivityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_id: str
    baseline_inputs: dict[str, Any]
    series: list[SensitivitySeries]
    disclaimer: str = (
        "Deterministic one-at-a-time sensitivity. Not a statistical forecast. "
        "Represents the effect of changing one input while holding others constant."
    )


# --- Simulate (non-persisted) ---------------------------------------------


class SimulateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_id: str
    inputs: dict[str, Any]


class SimulateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: ScenarioResult
    sensitivity: SensitivityResponse | None = None


__all__ = [
    "ManufacturingInputs",
    "InventoryInputs",
    "ServiceInputs",
    "ScenarioInputs",
    "ScenarioResult",
    "ScenarioCreate",
    "ScenarioRead",
    "ScenarioCompareRequest",
    "ScenarioComparison",
    "ScenarioComparisonRow",
    "SensitivityAxis",
    "SensitivityRequest",
    "SensitivityPoint",
    "SensitivitySeries",
    "SensitivityResponse",
    "SimulateRequest",
    "SimulateResponse",
]


# --- Helper for re-parsing inputs by industry -----------------------------


def parse_inputs_dict(payload: dict[str, Any]) -> ScenarioInputs:
    """Coerce a generic dict to the right inputs model based on ``industry``."""
    industry = payload.get("industry")
    if industry == Industry.MANUFACTURING.value:
        return ManufacturingInputs.model_validate(payload)
    if industry == Industry.SERVICE.value:
        return ServiceInputs.model_validate(payload)
    if industry in {Industry.RETAIL.value, Industry.WHOLESALE.value, Industry.FOOD.value}:
        return InventoryInputs.model_validate(payload)
    raise ValueError(f"Unknown industry: {industry!r}")
