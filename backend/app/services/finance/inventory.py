"""Inventory and production calculations.

These are the manufacturing-clothing-style calculations. They are pure
functions of typed inputs; the calling layer (the industry adapter) maps
scenario input dicts to the typed parameters below.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.finance.money import ZERO, add, format_money, mul, quantize, sub


@dataclass(frozen=True)
class ManufacturingInputs:
    """Typed inputs for a single-period manufacturing scenario."""

    opening_raw_material_qty: Decimal
    planned_raw_material_purchase_qty: Decimal
    material_unit_cost: Decimal
    material_per_unit: Decimal
    material_waste_pct: Decimal
    planned_production_qty: Decimal
    production_capacity_qty: Decimal
    labor_cost_per_unit: Decimal
    other_variable_cost_per_unit: Decimal
    selling_price: Decimal
    expected_units_sold: Decimal
    operating_expenses: Decimal
    customer_payment_delay_periods: int
    supplier_payment_delay_periods: int
    horizon_months: int
    currency: str
    opening_cash: Decimal


@dataclass(frozen=True)
class ManufacturingResult:
    currency: str
    feasible_production: Decimal
    units_produced: Decimal
    units_sold: Decimal
    units_unsold: Decimal
    material_used: Decimal
    material_unused: Decimal
    material_shortage: Decimal
    capacity_exceeded: Decimal
    cost_of_goods_sold: Decimal
    unsold_inventory_value: Decimal
    revenue: Decimal
    gross_profit: Decimal
    operating_profit: Decimal
    cash_inflows: Decimal
    cash_outflows: Decimal
    net_cash_movement: Decimal
    closing_cash: Decimal
    minimum_projected_cash: Decimal
    warnings: list[str]


def run_manufacturing(inp: ManufacturingInputs) -> ManufacturingResult:
    """Run the deterministic manufacturing scenario.

    See ``docs/FINANCIAL_MODEL.md`` §5 for the exact formulas. The output
    is a :class:`ManufacturingResult` with every quantity needed for the
    dashboard and decision engine.
    """
    currency = inp.currency

    # 1. Raw material availability and requirement
    available_raw_material = add(
        inp.opening_raw_material_qty, inp.planned_raw_material_purchase_qty, currency
    )
    waste_multiplier = add(Decimal("1"), inp.material_waste_pct, currency)
    material_required = mul(inp.planned_production_qty * inp.material_per_unit, waste_multiplier, currency)

    # 2. Material-bounded production quantity (ignoring capacity)
    if inp.material_per_unit == ZERO:
        material_bounded = inp.planned_production_qty
    else:
        # feasible_production_by_material = floor(available / (material_per_unit * (1 + waste)))
        denom = inp.material_per_unit * waste_multiplier
        material_bounded = (
            available_raw_material / denom if denom > ZERO else inp.planned_production_qty
        ).to_integral_value(rounding="ROUND_FLOOR")

    # 3. Capacity-bounded production
    capacity_bounded = min(inp.planned_production_qty, inp.production_capacity_qty)

    # 4. Feasible production is min of planned, capacity, material-bounded
    feasible = min(inp.planned_production_qty, capacity_bounded, material_bounded)

    # 5. Material used and unused
    material_used = mul(feasible * inp.material_per_unit, waste_multiplier, currency)
    material_unused = sub(available_raw_material, material_used, currency)
    if material_unused < ZERO:
        material_unused = ZERO

    # 6. Material shortage if planned_production > feasible
    material_shortage = sub(material_required, material_used, currency)
    if material_shortage < ZERO:
        material_shortage = ZERO

    # 7. Capacity exceeded if planned_production > capacity
    capacity_exceeded = sub(inp.planned_production_qty, inp.production_capacity_qty, currency)
    if capacity_exceeded < ZERO:
        capacity_exceeded = ZERO

    # 8. Units sold (capped by production)
    units_sold = min(inp.expected_units_sold, feasible)
    units_unsold = sub(feasible, units_sold, currency)

    # 9. Unit cost (FIFO, includes labor + other variable + material with waste)
    unit_material_cost = mul(
        inp.material_per_unit * inp.material_unit_cost, waste_multiplier, currency
    )
    unit_variable_cost = add(
        unit_material_cost, inp.labor_cost_per_unit, currency
    )
    unit_variable_cost = add(unit_variable_cost, inp.other_variable_cost_per_unit, currency)

    # 10. COGS based on units actually sold
    cogs = mul(units_sold * unit_variable_cost, Decimal("1"), currency)

    # 11. Unsold inventory carrying value (same unit cost)
    unsold_inventory_value = mul(units_unsold * unit_variable_cost, Decimal("1"), currency)

    # 12. Revenue
    revenue = mul(units_sold * inp.selling_price, Decimal("1"), currency)

    # 13. Gross profit and operating profit
    gross_profit = sub(revenue, cogs, currency)
    # Operating expenses apply even if no units sold.
    operating_profit = sub(gross_profit, inp.operating_expenses, currency)

    # 14. Cash flow schedule (single-period simplification)
    # Cash inflow from sales delayed by customer_payment_delay_periods.
    # Cash outflow for materials delayed by supplier_payment_delay_periods.
    # For a 1-period horizon, we treat supplier payment at period 0 (immediate),
    # customer payment at period `customer_payment_delay_periods`.
    cash_outflows_mat = mul(
        inp.planned_raw_material_purchase_qty * inp.material_unit_cost,
        Decimal("1"),
        currency,
    )
    labor_cash = mul(feasible * inp.labor_cost_per_unit, Decimal("1"), currency)
    other_var_cash = mul(feasible * inp.other_variable_cost_per_unit, Decimal("1"), currency)
    total_cash_out = add(cash_outflows_mat, labor_cash, currency)
    total_cash_out = add(total_cash_out, other_var_cash, currency)
    total_cash_out = add(total_cash_out, inp.operating_expenses, currency)

    # Schedule cash flow over the horizon.
    period_cash: list[Decimal] = [ZERO] * inp.horizon_months
    # Supplier pays at supplier_payment_delay_periods
    s_delay = min(inp.supplier_payment_delay_periods, inp.horizon_months - 1)
    period_cash[s_delay] = sub(period_cash[s_delay], total_cash_out, currency)
    # Customer pays at customer_payment_delay_periods
    c_delay = min(inp.customer_payment_delay_periods, inp.horizon_months - 1)
    period_cash[c_delay] = add(period_cash[c_delay], revenue, currency)

    opening = inp.opening_cash
    running_cash = opening
    min_cash = opening
    for change in period_cash:
        running_cash = add(running_cash, change, currency)
        if running_cash < min_cash:
            min_cash = running_cash

    closing_cash = running_cash
    net_cash = sub(closing_cash, opening, currency)
    cash_inflows = revenue if c_delay < inp.horizon_months else ZERO

    warnings: list[str] = []
    if material_shortage > ZERO:
        warnings.append(
            f"Material shortage: {format_money(material_shortage, currency)} of material "
            f"unavailable for the planned production."
        )
    if capacity_exceeded > ZERO:
        warnings.append(
            f"Capacity exceeded: {format_money(inp.planned_production_qty - inp.production_capacity_qty, currency)} "
            f"units of production requested beyond the stated capacity."
        )
    if closing_cash < ZERO:
        warnings.append(
            f"Projected closing cash is negative: {format_money(closing_cash, currency)}."
        )
    if min_cash < ZERO:
        warnings.append(
            f"Projected cash dips below zero during the horizon (minimum {format_money(min_cash, currency)})."
        )

    return ManufacturingResult(
        currency=currency,
        feasible_production=feasible,
        units_produced=feasible,
        units_sold=units_sold,
        units_unsold=units_unsold,
        material_used=material_used,
        material_unused=material_unused,
        material_shortage=material_shortage,
        capacity_exceeded=capacity_exceeded,
        cost_of_goods_sold=cogs,
        unsold_inventory_value=unsold_inventory_value,
        revenue=revenue,
        gross_profit=gross_profit,
        operating_profit=operating_profit,
        cash_inflows=cash_inflows,
        cash_outflows=total_cash_out,
        net_cash_movement=net_cash,
        closing_cash=closing_cash,
        minimum_projected_cash=min_cash,
        warnings=warnings,
    )


# --- Inventory (retail / wholesale / food) ---------------------------------


@dataclass(frozen=True)
class InventoryInputs:
    opening_inventory_units: Decimal
    planned_purchase_units: Decimal
    purchase_unit_cost: Decimal
    selling_price: Decimal
    expected_units_sold: Decimal
    shrinkage_pct: Decimal
    operating_expenses: Decimal
    supplier_payment_delay_periods: int
    customer_payment_delay_periods: int
    horizon_months: int
    currency: str
    opening_cash: Decimal


@dataclass(frozen=True)
class InventoryResult:
    currency: str
    available_units: Decimal
    units_sold: Decimal
    units_unsold: Decimal
    cogs: Decimal
    revenue: Decimal
    gross_profit: Decimal
    operating_profit: Decimal
    closing_inventory_units: Decimal
    closing_inventory_value: Decimal
    cash_inflows: Decimal
    cash_outflows: Decimal
    net_cash_movement: Decimal
    closing_cash: Decimal
    minimum_projected_cash: Decimal
    warnings: list[str]


def run_inventory(inp: InventoryInputs) -> InventoryResult:
    currency = inp.currency
    shrink_multiplier = sub(Decimal("1"), inp.shrinkage_pct, currency)
    available_units = mul(inp.planned_purchase_units, shrink_multiplier, currency)
    available_units = add(available_units, inp.opening_inventory_units, currency)

    units_sold = min(inp.expected_units_sold, available_units)
    units_unsold = sub(available_units, units_sold, currency)
    cogs = mul(units_sold, inp.purchase_unit_cost, currency)
    revenue = mul(units_sold, inp.selling_price, currency)
    gross_profit = sub(revenue, cogs, currency)
    operating_profit = sub(gross_profit, inp.operating_expenses, currency)

    purchase_cash_out = mul(inp.planned_purchase_units, inp.purchase_unit_cost, currency)
    total_cash_out = add(purchase_cash_out, inp.operating_expenses, currency)

    period_cash: list[Decimal] = [ZERO] * inp.horizon_months
    s_delay = min(inp.supplier_payment_delay_periods, inp.horizon_months - 1)
    period_cash[s_delay] = sub(period_cash[s_delay], total_cash_out, currency)
    c_delay = min(inp.customer_payment_delay_periods, inp.horizon_months - 1)
    period_cash[c_delay] = add(period_cash[c_delay], revenue, currency)

    running = inp.opening_cash
    min_cash = inp.opening_cash
    for change in period_cash:
        running = add(running, change, currency)
        if running < min_cash:
            min_cash = running
    closing_cash = running
    net_cash = sub(closing_cash, inp.opening_cash, currency)
    cash_inflows = revenue if c_delay < inp.horizon_months else ZERO

    closing_inventory_units = units_unsold
    closing_inventory_value = mul(units_unsold, inp.purchase_unit_cost, currency)

    warnings: list[str] = []
    if closing_cash < ZERO:
        warnings.append(f"Projected closing cash is negative: {format_money(closing_cash, currency)}.")
    if min_cash < ZERO:
        warnings.append(
            f"Projected cash dips below zero during the horizon (minimum {format_money(min_cash, currency)})."
        )

    return InventoryResult(
        currency=currency,
        available_units=available_units,
        units_sold=units_sold,
        units_unsold=units_unsold,
        cogs=cogs,
        revenue=revenue,
        gross_profit=gross_profit,
        operating_profit=operating_profit,
        closing_inventory_units=closing_inventory_units,
        closing_inventory_value=closing_inventory_value,
        cash_inflows=cash_inflows,
        cash_outflows=total_cash_out,
        net_cash_movement=net_cash,
        closing_cash=closing_cash,
        minimum_projected_cash=min_cash,
        warnings=warnings,
    )


# --- Service ----------------------------------------------------------------


@dataclass(frozen=True)
class ServiceInputs:
    billable_hours_capacity: Decimal
    planned_billable_utilization_pct: Decimal
    hourly_price: Decimal
    project_revenue: Decimal | None
    labor_cost_per_hour: Decimal
    contractor_cost: Decimal
    project_expenses: Decimal
    operating_expenses: Decimal
    invoice_payment_delay_periods: int
    horizon_months: int
    currency: str
    opening_cash: Decimal


@dataclass(frozen=True)
class ServiceResult:
    currency: str
    billable_hours: Decimal
    revenue: Decimal
    labor_cost: Decimal
    contribution_margin: Decimal
    operating_profit: Decimal
    cash_inflows: Decimal
    cash_outflows: Decimal
    net_cash_movement: Decimal
    closing_cash: Decimal
    minimum_projected_cash: Decimal
    warnings: list[str]


def run_service(inp: ServiceInputs) -> ServiceResult:
    currency = inp.currency
    billable_hours = mul(inp.billable_hours_capacity, inp.planned_billable_utilization_pct, currency)
    hourly_revenue = mul(billable_hours, inp.hourly_price, currency)
    if inp.project_revenue is not None and inp.project_revenue > hourly_revenue:
        revenue = inp.project_revenue
    else:
        revenue = hourly_revenue
    labor_cost = mul(billable_hours, inp.labor_cost_per_hour, currency)
    contribution = sub(
        sub(sub(revenue, labor_cost, currency), inp.contractor_cost, currency),
        inp.project_expenses,
        currency,
    )
    operating_profit = sub(contribution, inp.operating_expenses, currency)

    total_cash_out = add(add(labor_cost, inp.contractor_cost, currency), inp.project_expenses, currency)
    total_cash_out = add(total_cash_out, inp.operating_expenses, currency)

    period_cash: list[Decimal] = [ZERO] * inp.horizon_months
    c_delay = min(inp.invoice_payment_delay_periods, inp.horizon_months - 1)
    period_cash[c_delay] = add(period_cash[c_delay], revenue, currency)
    # Labor / opex paid at period 0
    period_cash[0] = sub(period_cash[0], total_cash_out, currency)

    running = inp.opening_cash
    min_cash = inp.opening_cash
    for change in period_cash:
        running = add(running, change, currency)
        if running < min_cash:
            min_cash = running
    closing_cash = running
    net_cash = sub(closing_cash, inp.opening_cash, currency)
    cash_inflows = revenue if c_delay < inp.horizon_months else ZERO

    warnings: list[str] = []
    if contribution < ZERO:
        warnings.append("Contribution margin is negative; revenue does not cover variable costs.")
    if closing_cash < ZERO:
        warnings.append(f"Projected closing cash is negative: {format_money(closing_cash, currency)}.")

    return ServiceResult(
        currency=currency,
        billable_hours=billable_hours,
        revenue=revenue,
        labor_cost=labor_cost,
        contribution_margin=contribution,
        operating_profit=operating_profit,
        cash_inflows=cash_inflows,
        cash_outflows=total_cash_out,
        net_cash_movement=net_cash,
        closing_cash=closing_cash,
        minimum_projected_cash=min_cash,
        warnings=warnings,
    )


__all__ = [
    "ManufacturingInputs",
    "ManufacturingResult",
    "run_manufacturing",
    "InventoryInputs",
    "InventoryResult",
    "run_inventory",
    "ServiceInputs",
    "ServiceResult",
    "run_service",
]