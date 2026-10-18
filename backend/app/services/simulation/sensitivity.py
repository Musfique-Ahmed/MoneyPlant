"""Sensitivity analysis.

One-at-a-time deterministic sensitivity for a fixed set of axes. The
output is labelled "deterministic sensitivity — not a statistical
forecast" and the multipliers are bounded (default ±25%) to discourage
unreasonable extrapolation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.schemas.finance import (
    ScenarioResult,
    SensitivityAxis,
    SensitivityPoint,
    SensitivityResponse,
    SensitivitySeries,
)
from app.services.finance.money import format_money
from app.services.simulation.runner import run_scenario

DEFAULT_MULTIPLIERS: tuple[str, ...] = ("-0.25", "-0.10", "0", "0.10", "0.25")


def _shift(value: str | Decimal, multiplier: Decimal) -> str:
    d = Decimal(str(value))
    return str(d + d * multiplier)


def _axis_for(industry: str, axis: SensitivityAxis) -> str | None:
    """Return the input field name to shift for a given (industry, axis)."""
    if industry == "manufacturing":
        mapping = {
            SensitivityAxis.SALES_VOLUME: "expected_units_sold",
            SensitivityAxis.SELLING_PRICE: "selling_price",
            SensitivityAxis.MATERIAL_COST: "material_unit_cost",
            SensitivityAxis.LABOR_COST: "labor_cost_per_unit",
            SensitivityAxis.CUSTOMER_PAYMENT_DELAY: "customer_payment_delay_periods",
            SensitivityAxis.SUPPLIER_PAYMENT_DELAY: "supplier_payment_delay_periods",
            SensitivityAxis.WASTE: "material_waste_pct",
            SensitivityAxis.OPEX: "operating_expenses",
        }
    elif industry in {"retail", "wholesale", "food"}:
        mapping = {
            SensitivityAxis.SALES_VOLUME: "expected_units_sold",
            SensitivityAxis.SELLING_PRICE: "selling_price",
            SensitivityAxis.MATERIAL_COST: "purchase_unit_cost",
            SensitivityAxis.LABOR_COST: None,  # not a direct lever
            SensitivityAxis.CUSTOMER_PAYMENT_DELAY: "customer_payment_delay_periods",
            SensitivityAxis.SUPPLIER_PAYMENT_DELAY: "supplier_payment_delay_periods",
            SensitivityAxis.WASTE: "shrinkage_pct",
            SensitivityAxis.OPEX: "operating_expenses",
        }
    else:  # service
        mapping = {
            SensitivityAxis.SALES_VOLUME: "planned_billable_utilization_pct",
            SensitivityAxis.SELLING_PRICE: "hourly_price",
            SensitivityAxis.MATERIAL_COST: None,
            SensitivityAxis.LABOR_COST: "labor_cost_per_hour",
            SensitivityAxis.CUSTOMER_PAYMENT_DELAY: "invoice_payment_delay_periods",
            SensitivityAxis.SUPPLIER_PAYMENT_DELAY: None,
            SensitivityAxis.WASTE: None,
            SensitivityAxis.OPEX: "operating_expenses",
        }
    return mapping.get(axis)


def _delay_shift(value: str | int, multiplier: Decimal) -> int:
    base = int(value)
    if multiplier == 0:
        return base
    return max(0, base + int(Decimal("30") * multiplier))


def run_sensitivity(
    business_id: str,
    inputs: dict[str, Any],
    currency: str,
    axes: list[SensitivityAxis] | None = None,
    multipliers: list[str] | None = None,
) -> SensitivityResponse:
    if not axes:
        axes = [
            SensitivityAxis.SALES_VOLUME,
            SensitivityAxis.SELLING_PRICE,
            SensitivityAxis.OPEX,
        ]
    multipliers = multipliers or list(DEFAULT_MULTIPLIERS)

    series: list[SensitivitySeries] = []
    for axis in axes:
        field = _axis_for(inputs["industry"], axis)
        if field is None:
            continue
        is_delay = axis in {
            SensitivityAxis.CUSTOMER_PAYMENT_DELAY,
            SensitivityAxis.SUPPLIER_PAYMENT_DELAY,
        }
        points: list[SensitivityPoint] = []
        for m_str in multipliers:
            m = Decimal(m_str)
            shifted_inputs = dict(inputs)
            if is_delay:
                shifted_inputs[field] = _delay_shift(inputs[field], m)
            else:
                shifted_inputs[field] = _shift(inputs[field], m)
            result: ScenarioResult = run_scenario(shifted_inputs, currency)
            points.append(
                SensitivityPoint(
                    multiplier=m_str,
                    revenue=result.revenue,
                    operating_profit=result.operating_profit,
                    closing_cash=result.closing_cash,
                    minimum_projected_cash=result.minimum_projected_cash,
                )
            )
        series.append(SensitivitySeries(axis=axis, points=points))

    return SensitivityResponse(
        business_id=business_id,
        baseline_inputs=inputs,
        series=series,
    )


__all__ = ["run_sensitivity", "DEFAULT_MULTIPLIERS"]