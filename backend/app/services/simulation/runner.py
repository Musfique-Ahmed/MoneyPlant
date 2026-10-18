"""Scenario runner.

Single entry point that:

1. Validates the input dict via the right industry adapter.
2. Builds the typed engine inputs.
3. Runs the engine.
4. Asserts invariants.
5. Returns a typed :class:`ScenarioResult` ready for the API.

The runner has no awareness of the database — it operates on the
validated input dict and the configured business settings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.schemas.business import Industry
from app.schemas.finance import (
    ManufacturingInputs,
    ScenarioResult,
    ServiceInputs,
    parse_inputs_dict,
)
from app.services.finance.inventory import (
    InventoryInputs as EngineInventoryInputs,
    ManufacturingInputs as EngineManufacturingInputs,
    ServiceInputs as EngineServiceInputs,
    run_inventory,
    run_manufacturing,
    run_service,
)
from app.services.finance.invariants import (
    assert_invariants,
    failures as invariant_failures,
)
from app.services.finance.money import (
    ZERO,
    format_money,
    quantize,
    safe_div_str,
)
from app.services.industry_adapters import get_adapter

ENGINE_VERSION = "0.1.0"


def _parse_decimal(value: str | int | float | Decimal, name: str) -> Decimal:
    if value is None or value == "":
        raise ValueError(f"Missing required input: {name}")
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"Invalid decimal for {name}: {value!r}") from exc


def _parse_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number, not a bool")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"Invalid integer for {name}: {value!r}") from exc
    raise ValueError(f"Invalid integer for {name}: {value!r}")


def run_scenario(inputs: dict[str, Any], currency: str) -> ScenarioResult:
    """Run a scenario and return the authoritative result.

    Raises :class:`ValueError` for invalid inputs (caught by the API layer
    and returned as 400 with the message).
    """
    industry = inputs.get("industry")
    if industry not in {i.value for i in Industry}:
        raise ValueError(f"Unknown industry: {industry!r}")
    adapter = get_adapter(industry)
    adapter.validate_inputs(inputs)

    if industry == Industry.MANUFACTURING.value:
        mi = ManufacturingInputs.model_validate(inputs)
        opening_cash = _parse_decimal(mi.opening_cash, "opening_cash")
        engine_in = EngineManufacturingInputs(
            opening_raw_material_qty=_parse_decimal(mi.opening_raw_material_qty, "opening_raw_material_qty"),
            planned_raw_material_purchase_qty=_parse_decimal(
                mi.planned_raw_material_purchase_qty, "planned_raw_material_purchase_qty"
            ),
            material_unit_cost=_parse_decimal(mi.material_unit_cost, "material_unit_cost"),
            material_per_unit=_parse_decimal(mi.material_per_unit, "material_per_unit"),
            material_waste_pct=_parse_decimal(mi.material_waste_pct, "material_waste_pct"),
            planned_production_qty=_parse_decimal(mi.planned_production_qty, "planned_production_qty"),
            production_capacity_qty=_parse_decimal(
                mi.production_capacity_qty, "production_capacity_qty"
            ),
            labor_cost_per_unit=_parse_decimal(mi.labor_cost_per_unit, "labor_cost_per_unit"),
            other_variable_cost_per_unit=_parse_decimal(
                mi.other_variable_cost_per_unit, "other_variable_cost_per_unit"
            ),
            selling_price=_parse_decimal(mi.selling_price, "selling_price"),
            expected_units_sold=_parse_decimal(mi.expected_units_sold, "expected_units_sold"),
            operating_expenses=_parse_decimal(mi.operating_expenses, "operating_expenses"),
            customer_payment_delay_periods=_parse_int(
                mi.customer_payment_delay_periods, "customer_payment_delay_periods"
            ),
            supplier_payment_delay_periods=_parse_int(
                mi.supplier_payment_delay_periods, "supplier_payment_delay_periods"
            ),
            horizon_months=_parse_int(mi.horizon_months, "horizon_months"),
            currency=currency,
            opening_cash=opening_cash,
        )
        r = run_manufacturing(engine_in)
        available_material = quantize(
            engine_in.opening_raw_material_qty + engine_in.planned_raw_material_purchase_qty, currency
        )
        inv = assert_invariants(
            opening_cash=opening_cash,
            closing_cash=r.closing_cash,
            cash_inflows=r.cash_inflows,
            cash_outflows=r.cash_outflows,
            currency=currency,
            units_sold=r.units_sold,
            units_produced=r.units_produced,
            material_used=r.material_used,
            available_material=available_material,
            feasible_production=r.feasible_production,
            production_capacity=engine_in.production_capacity_qty,
            revenue=r.revenue,
            selling_price=engine_in.selling_price,
        )
        return ScenarioResult(
            engine_version=ENGINE_VERSION,
            calculation_timestamp=datetime.now(timezone.utc),
            currency=r.currency,
            revenue=format_money(r.revenue, r.currency),
            direct_costs=format_money(r.cost_of_goods_sold, r.currency),
            gross_profit=format_money(r.gross_profit, r.currency),
            gross_margin=safe_div_str(r.gross_profit, r.revenue, r.currency, places=4),
            operating_expenses=format_money(engine_in.operating_expenses, r.currency),
            operating_profit=format_money(r.operating_profit, r.currency),
            operating_margin=safe_div_str(r.operating_profit, r.revenue, r.currency, places=4),
            cash_inflows=format_money(r.cash_inflows, r.currency),
            cash_outflows=format_money(r.cash_outflows, r.currency),
            net_cash_movement=format_money(r.net_cash_movement, r.currency),
            opening_cash=format_money(opening_cash, r.currency),
            closing_cash=format_money(r.closing_cash, r.currency),
            minimum_projected_cash=format_money(r.minimum_projected_cash, r.currency),
            cash_runway_months=(
                format_money(r.closing_cash / r.cash_outflows, r.currency)
                if r.cash_outflows > ZERO
                else None
            ),
            contribution_margin=format_money(r.gross_profit - engine_in.operating_expenses, r.currency),
            units_sold=str(r.units_sold),
            units_produced=str(r.units_produced),
            unsold_inventory_units=str(r.units_unsold),
            unsold_inventory_value=format_money(r.unsold_inventory_value, r.currency),
            material_shortage=format_money(r.material_shortage, r.currency),
            feasible_production=str(r.feasible_production),
            warnings=r.warnings,
            invariants_ok=not invariant_failures(inv),
            invariants_failures=[f"{c.name}: {c.detail}" for c in invariant_failures(inv)],
        )

    if industry == Industry.SERVICE.value:
        si = ServiceInputs.model_validate(inputs)
        engine_in = EngineServiceInputs(
            billable_hours_capacity=_parse_decimal(si.billable_hours_capacity, "billable_hours_capacity"),
            planned_billable_utilization_pct=_parse_decimal(
                si.planned_billable_utilization_pct, "planned_billable_utilization_pct"
            ),
            hourly_price=_parse_decimal(si.hourly_price, "hourly_price"),
            project_revenue=(
                _parse_decimal(si.project_revenue, "project_revenue") if si.project_revenue else None
            ),
            labor_cost_per_hour=_parse_decimal(si.labor_cost_per_hour, "labor_cost_per_hour"),
            contractor_cost=_parse_decimal(si.contractor_cost, "contractor_cost"),
            project_expenses=_parse_decimal(si.project_expenses, "project_expenses"),
            operating_expenses=_parse_decimal(si.operating_expenses, "operating_expenses"),
            invoice_payment_delay_periods=_parse_int(
                si.invoice_payment_delay_periods, "invoice_payment_delay_periods"
            ),
            horizon_months=_parse_int(si.horizon_months, "horizon_months"),
            currency=currency,
            opening_cash=_parse_decimal(si.opening_cash, "opening_cash"),
        )
        r = run_service(engine_in)
        inv = assert_invariants(
            opening_cash=engine_in.opening_cash,
            closing_cash=r.closing_cash,
            cash_inflows=r.cash_inflows,
            cash_outflows=r.cash_outflows,
            currency=currency,
        )
        return ScenarioResult(
            engine_version=ENGINE_VERSION,
            calculation_timestamp=datetime.now(timezone.utc),
            currency=r.currency,
            revenue=format_money(r.revenue, r.currency),
            direct_costs=format_money(r.labor_cost, r.currency),
            gross_profit=format_money(r.contribution_margin + r.labor_cost, r.currency),
            gross_margin=safe_div_str(r.contribution_margin + r.labor_cost, r.revenue, r.currency, places=4),
            operating_expenses=format_money(engine_in.operating_expenses, r.currency),
            operating_profit=format_money(r.operating_profit, r.currency),
            operating_margin=safe_div_str(r.operating_profit, r.revenue, r.currency, places=4),
            cash_inflows=format_money(r.cash_inflows, r.currency),
            cash_outflows=format_money(r.cash_outflows, r.currency),
            net_cash_movement=format_money(r.net_cash_movement, r.currency),
            opening_cash=format_money(engine_in.opening_cash, r.currency),
            closing_cash=format_money(r.closing_cash, r.currency),
            minimum_projected_cash=format_money(r.minimum_projected_cash, r.currency),
            cash_runway_months=(
                format_money(r.closing_cash / r.cash_outflows, r.currency)
                if r.cash_outflows > ZERO
                else None
            ),
            contribution_margin=format_money(r.contribution_margin, r.currency),
            warnings=r.warnings,
            invariants_ok=not invariant_failures(inv),
            invariants_failures=[f"{c.name}: {c.detail}" for c in invariant_failures(inv)],
        )

    # Inventory-based: retail / wholesale / food
    from app.schemas.finance import InventoryInputs as SchemaInventoryInputs

    ii = SchemaInventoryInputs.model_validate(inputs)
    engine_in = EngineInventoryInputs(
        opening_inventory_units=_parse_decimal(ii.opening_inventory_units, "opening_inventory_units"),
        planned_purchase_units=_parse_decimal(ii.planned_purchase_units, "planned_purchase_units"),
        purchase_unit_cost=_parse_decimal(ii.purchase_unit_cost, "purchase_unit_cost"),
        selling_price=_parse_decimal(ii.selling_price, "selling_price"),
        expected_units_sold=_parse_decimal(ii.expected_units_sold, "expected_units_sold"),
        shrinkage_pct=_parse_decimal(ii.shrinkage_pct, "shrinkage_pct"),
        operating_expenses=_parse_decimal(ii.operating_expenses, "operating_expenses"),
        supplier_payment_delay_periods=_parse_int(
            ii.supplier_payment_delay_periods, "supplier_payment_delay_periods"
        ),
        customer_payment_delay_periods=_parse_int(
            ii.customer_payment_delay_periods, "customer_payment_delay_periods"
        ),
        horizon_months=_parse_int(ii.horizon_months, "horizon_months"),
        currency=currency,
        opening_cash=_parse_decimal(ii.opening_cash, "opening_cash"),
    )
    r = run_inventory(engine_in)
    inv = assert_invariants(
        opening_cash=engine_in.opening_cash,
        closing_cash=r.closing_cash,
        cash_inflows=r.cash_inflows,
        cash_outflows=r.cash_outflows,
        currency=currency,
        units_sold=r.units_sold,
        units_produced=r.available_units,
        revenue=r.revenue,
        selling_price=engine_in.selling_price,
    )
    return ScenarioResult(
        engine_version=ENGINE_VERSION,
        calculation_timestamp=datetime.now(timezone.utc),
        currency=r.currency,
        revenue=format_money(r.revenue, r.currency),
        direct_costs=format_money(r.cogs, r.currency),
        gross_profit=format_money(r.gross_profit, r.currency),
        gross_margin=safe_div_str(r.gross_profit, r.revenue, r.currency, places=4),
        operating_expenses=format_money(engine_in.operating_expenses, r.currency),
        operating_profit=format_money(r.operating_profit, r.currency),
        operating_margin=safe_div_str(r.operating_profit, r.revenue, r.currency, places=4),
        cash_inflows=format_money(r.cash_inflows, r.currency),
        cash_outflows=format_money(r.cash_outflows, r.currency),
        net_cash_movement=format_money(r.net_cash_movement, r.currency),
        opening_cash=format_money(engine_in.opening_cash, r.currency),
        closing_cash=format_money(r.closing_cash, r.currency),
        minimum_projected_cash=format_money(r.minimum_projected_cash, r.currency),
        cash_runway_months=(
            format_money(r.closing_cash / r.cash_outflows, r.currency)
            if r.cash_outflows > ZERO
            else None
        ),
        contribution_margin=format_money(r.gross_profit - engine_in.operating_expenses, r.currency),
        units_sold=str(r.units_sold),
        units_produced=str(r.available_units),
        unsold_inventory_units=str(r.units_unsold),
        unsold_inventory_value=format_money(r.closing_inventory_value, r.currency),
        material_shortage=None,
        feasible_production=None,
        warnings=r.warnings,
        invariants_ok=not invariant_failures(inv),
        invariants_failures=[f"{c.name}: {c.detail}" for c in invariant_failures(inv)],
    )


__all__ = ["run_scenario", "ENGINE_VERSION"]