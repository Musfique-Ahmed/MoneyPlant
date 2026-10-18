"""Manufacturing, inventory, and service engine tests.

These assert the exact formulas described in docs/FINANCIAL_MODEL.md. They are
the contract that every other layer (simulation, rules, AI explanation) depends
on — so the math is checked here, not at integration level.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.finance.inventory import (
    InventoryInputs,
    ManufacturingInputs,
    ServiceInputs,
    run_inventory,
    run_manufacturing,
    run_service,
)


def _manufacturing_defaults() -> dict:
    return dict(
        opening_raw_material_qty=Decimal("100"),
        planned_raw_material_purchase_qty=Decimal("200"),
        material_unit_cost=Decimal("5.00"),
        material_per_unit=Decimal("2"),
        material_waste_pct=Decimal("0.10"),
        planned_production_qty=Decimal("100"),
        production_capacity_qty=Decimal("120"),
        labor_cost_per_unit=Decimal("3.00"),
        other_variable_cost_per_unit=Decimal("1.00"),
        selling_price=Decimal("20.00"),
        expected_units_sold=Decimal("90"),
        operating_expenses=Decimal("200.00"),
        customer_payment_delay_periods=1,
        supplier_payment_delay_periods=0,
        horizon_months=2,
        currency="USD",
        opening_cash=Decimal("1000.00"),
    )


def test_manufacturing_feasible_when_material_and_capacity_cover_planned() -> None:
    inp = ManufacturingInputs(**_manufacturing_defaults())
    r = run_manufacturing(inp)

    # available raw material: 100 + 200 = 300
    # material required for 100 units with 10% waste: 100 * 2 * 1.1 = 220
    # feasible: min(100, 120, floor(300/2.2)=136) = 100
    assert r.feasible_production == Decimal("100")
    assert r.units_produced == Decimal("100")
    assert r.units_sold == Decimal("90")
    assert r.units_unsold == Decimal("10")
    assert r.material_used == Decimal("220.00")
    assert r.material_unused == Decimal("80.00")
    assert r.material_shortage == Decimal("0.00")
    assert r.capacity_exceeded == Decimal("0.00")

    # unit_material_cost = 2 * 5.00 * 1.1 = 11.00
    # unit_variable_cost = 11.00 + 3.00 + 1.00 = 15.00
    # cogs = 90 * 15.00 = 1350.00
    # unsold value = 10 * 15.00 = 150.00
    # revenue = 90 * 20.00 = 1800.00
    # gross = 1800 - 1350 = 450.00
    # operating = 450 - 200 = 250.00
    assert r.cost_of_goods_sold == Decimal("1350.00")
    assert r.unsold_inventory_value == Decimal("150.00")
    assert r.revenue == Decimal("1800.00")
    assert r.gross_profit == Decimal("450.00")
    assert r.operating_profit == Decimal("250.00")

    # Cash timing: supplier pays at period 0, customer pays at period 1.
    # period 0: -total_cash_out ; period 1: +revenue
    # total_cash_out = (200 * 5.00) + (100 * 3.00) + (100 * 1.00) + 200 = 1000 + 300 + 100 + 200 = 1600
    # period 0 cash: 1000 - 1600 = -600
    # period 1 cash: -600 + 1800 = 1200
    # closing = 1200
    assert r.cash_outflows == Decimal("1600.00")
    assert r.cash_inflows == Decimal("1800.00")
    assert r.closing_cash == Decimal("1200.00")
    # min cash dipped to -600 during the horizon
    assert r.minimum_projected_cash == Decimal("-600.00")
    assert any("below zero" in w.lower() for w in r.warnings)


def test_manufacturing_capacity_bottleneck_caps_production() -> None:
    kw = _manufacturing_defaults()
    kw["planned_production_qty"] = Decimal("150")
    kw["production_capacity_qty"] = Decimal("80")
    inp = ManufacturingInputs(**kw)
    r = run_manufacturing(inp)

    # feasible: min(150, 80, 136) = 80
    assert r.feasible_production == Decimal("80")
    assert r.units_produced == Decimal("80")
    # capacity_exceeded = 150 - 80 = 70
    assert r.capacity_exceeded == Decimal("70")
    assert any("capacity exceeded" in w.lower() for w in r.warnings)


def test_manufacturing_material_bottleneck_caps_production() -> None:
    kw = _manufacturing_defaults()
    # Tiny material — only 5 units of material available, no purchase.
    kw["opening_raw_material_qty"] = Decimal("5")
    kw["planned_raw_material_purchase_qty"] = Decimal("0")
    kw["material_per_unit"] = Decimal("1")
    kw["material_waste_pct"] = Decimal("0")  # avoid inflating the requirement
    inp = ManufacturingInputs(**kw)
    r = run_manufacturing(inp)

    # feasible: min(100, 120, 5) = 5
    assert r.feasible_production == Decimal("5")
    assert r.units_produced == Decimal("5")
    # material_required for 100 units at 1:1 with 0% waste = 100
    # material_used = 5
    # material_shortage = 100 - 5 = 95
    assert r.material_shortage == Decimal("95")
    assert any("shortage" in w.lower() for w in r.warnings)


def test_manufacturing_sales_capped_by_production() -> None:
    kw = _manufacturing_defaults()
    kw["expected_units_sold"] = Decimal("500")  # more than feasible
    inp = ManufacturingInputs(**kw)
    r = run_manufacturing(inp)

    # units_sold is min(expected, feasible) = min(500, 100) = 100
    assert r.units_sold == Decimal("100")
    assert r.units_unsold == Decimal("0")


def test_manufacturing_payment_delays_both_delayed() -> None:
    kw = _manufacturing_defaults()
    kw["customer_payment_delay_periods"] = 0  # cash in at period 0
    kw["supplier_payment_delay_periods"] = 0  # cash out at period 0
    inp = ManufacturingInputs(**kw)
    r = run_manufacturing(inp)

    # period 0: revenue in (1800) - cash out (1600) = +200
    # closing = 1000 + 200 = 1200
    assert r.closing_cash == Decimal("1200.00")
    assert r.minimum_projected_cash == Decimal("1000.00")  # never dipped


def test_inventory_basic_case() -> None:
    inp = InventoryInputs(
        opening_inventory_units=Decimal("20"),
        planned_purchase_units=Decimal("100"),
        purchase_unit_cost=Decimal("5.00"),
        selling_price=Decimal("10.00"),
        expected_units_sold=Decimal("90"),
        shrinkage_pct=Decimal("0.10"),
        operating_expenses=Decimal("100.00"),
        supplier_payment_delay_periods=0,
        customer_payment_delay_periods=1,
        horizon_months=1,
        currency="USD",
        opening_cash=Decimal("500.00"),
    )
    r = run_inventory(inp)

    # available_units = 100 * (1 - 0.10) + 20 = 90 + 20 = 110
    # units_sold = min(90, 110) = 90
    # cogs = 90 * 5 = 450
    # revenue = 90 * 10 = 900
    # gross = 450 ; operating = 350
    assert r.available_units == Decimal("110")
    assert r.units_sold == Decimal("90")
    assert r.units_unsold == Decimal("20")
    assert r.cogs == Decimal("450.00")
    assert r.revenue == Decimal("900.00")
    assert r.gross_profit == Decimal("450.00")
    assert r.operating_profit == Decimal("350.00")
    # closing_inventory_value = 20 * 5 = 100
    assert r.closing_inventory_value == Decimal("100.00")


def test_inventory_shrinkage_can_make_unable_to_meet_demand() -> None:
    inp = InventoryInputs(
        opening_inventory_units=Decimal("0"),
        planned_purchase_units=Decimal("100"),
        purchase_unit_cost=Decimal("5.00"),
        selling_price=Decimal("10.00"),
        expected_units_sold=Decimal("120"),  # more than available
        shrinkage_pct=Decimal("0.50"),  # 50% shrink
        operating_expenses=Decimal("0"),
        supplier_payment_delay_periods=0,
        customer_payment_delay_periods=0,
        horizon_months=1,
        currency="USD",
        opening_cash=Decimal("0"),
    )
    r = run_inventory(inp)
    # available = 50; sold = min(120, 50) = 50
    assert r.available_units == Decimal("50")
    assert r.units_sold == Decimal("50")


def test_service_uses_billable_hours_x_price_when_no_project_revenue() -> None:
    inp = ServiceInputs(
        billable_hours_capacity=Decimal("100"),
        planned_billable_utilization_pct=Decimal("0.80"),
        hourly_price=Decimal("150.00"),
        project_revenue=None,
        labor_cost_per_hour=Decimal("60.00"),
        contractor_cost=Decimal("0"),
        project_expenses=Decimal("0"),
        operating_expenses=Decimal("200.00"),
        invoice_payment_delay_periods=1,
        horizon_months=2,
        currency="USD",
        opening_cash=Decimal("1000.00"),
    )
    r = run_service(inp)
    # billable_hours = 80 ; revenue = 80 * 150 = 12000
    # labor_cost = 80 * 60 = 4800 ; contribution = 12000 - 4800 = 7200
    # operating_profit = 7200 - 200 = 7000
    assert r.billable_hours == Decimal("80")
    assert r.revenue == Decimal("12000.00")
    assert r.labor_cost == Decimal("4800.00")
    assert r.contribution_margin == Decimal("7200.00")
    assert r.operating_profit == Decimal("7000.00")


def test_service_project_revenue_overrides_hourly_when_larger() -> None:
    inp = ServiceInputs(
        billable_hours_capacity=Decimal("10"),
        planned_billable_utilization_pct=Decimal("1.0"),
        hourly_price=Decimal("100.00"),  # would yield 1000
        project_revenue=Decimal("5000.00"),  # larger
        labor_cost_per_hour=Decimal("0"),
        contractor_cost=Decimal("0"),
        project_expenses=Decimal("0"),
        operating_expenses=Decimal("0"),
        invoice_payment_delay_periods=0,
        horizon_months=1,
        currency="USD",
        opening_cash=Decimal("0"),
    )
    r = run_service(inp)
    # hourly would be 1000 ; project_revenue 5000 > 1000 → use 5000
    assert r.revenue == Decimal("5000.00")


def test_service_negative_contribution_warns() -> None:
    inp = ServiceInputs(
        billable_hours_capacity=Decimal("10"),
        planned_billable_utilization_pct=Decimal("1.0"),
        hourly_price=Decimal("50.00"),
        project_revenue=None,
        labor_cost_per_hour=Decimal("100.00"),  # 1000 cost vs 500 revenue
        contractor_cost=Decimal("0"),
        project_expenses=Decimal("0"),
        operating_expenses=Decimal("0"),
        invoice_payment_delay_periods=0,
        horizon_months=1,
        currency="USD",
        opening_cash=Decimal("0"),
    )
    r = run_service(inp)
    assert r.contribution_margin == Decimal("-500.00")
    assert any("contribution margin" in w.lower() for w in r.warnings)
