"""End-to-end scenario runner tests.

These go through the full pipeline: input dict → adapter validation → engine →
invariant assertions → ScenarioResult. The numeric outputs must match exactly.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.simulation.runner import run_scenario


def _base_manufacturing_inputs() -> dict:
    return {
        "industry": "manufacturing",
        "opening_cash": "1000.00",
        "opening_raw_material_qty": "100",
        "planned_raw_material_purchase_qty": "200",
        "material_unit_cost": "5.00",
        "material_per_unit": "2",
        "material_waste_pct": "0.10",
        "planned_production_qty": "100",
        "production_capacity_qty": "120",
        "labor_cost_per_unit": "3.00",
        "other_variable_cost_per_unit": "1.00",
        "selling_price": "20.00",
        "expected_units_sold": "90",
        "operating_expenses": "200.00",
        "customer_payment_delay_periods": 1,
        "supplier_payment_delay_periods": 0,
        "horizon_months": 2,
    }


def test_manufacturing_scenario_full_run() -> None:
    r = run_scenario(_base_manufacturing_inputs(), "USD")
    assert r.currency == "USD"
    # revenue = 90 * 20 = 1800
    assert Decimal(r.revenue) == Decimal("1800.00")
    # cogs = 90 * (2*5*1.1 + 3 + 1) = 90 * 15 = 1350
    assert Decimal(r.direct_costs) == Decimal("1350.00")
    # gross = 450 ; operating = 250
    assert Decimal(r.gross_profit) == Decimal("450.00")
    assert Decimal(r.operating_profit) == Decimal("250.00")
    assert Decimal(r.operating_expenses) == Decimal("200.00")
    # cash in at period 1 = 1800; cash out at period 0 = 1600
    assert Decimal(r.cash_inflows) == Decimal("1800.00")
    assert Decimal(r.cash_outflows) == Decimal("1600.00")
    # closing = 1000 - 1600 + 1800 = 1200
    assert Decimal(r.closing_cash) == Decimal("1200.00")
    # min_cash = 1000 - 1600 = -600
    assert Decimal(r.minimum_projected_cash) == Decimal("-600.00")
    # Invariants should pass — this is a balanced scenario.
    assert r.invariants_ok
    assert r.invariants_failures == []
    # Warnings include the negative-cash note.
    assert any("below zero" in w.lower() for w in r.warnings)


def test_retail_scenario_full_run() -> None:
    r = run_scenario(
        {
            "industry": "retail",
            "opening_cash": "500.00",
            "opening_inventory_units": "20",
            "planned_purchase_units": "100",
            "purchase_unit_cost": "5.00",
            "selling_price": "10.00",
            "expected_units_sold": "90",
            "shrinkage_pct": "0.10",
            "operating_expenses": "100.00",
            "customer_payment_delay_periods": 0,
            "supplier_payment_delay_periods": 0,
            "horizon_months": 1,
        },
        "USD",
    )
    # available = 100 * 0.9 + 20 = 110
    # cogs = 90 * 5 = 450 ; revenue = 90 * 10 = 900
    # gross = 450 ; operating = 350
    assert Decimal(r.revenue) == Decimal("900.00")
    assert Decimal(r.direct_costs) == Decimal("450.00")
    assert Decimal(r.gross_profit) == Decimal("450.00")
    assert Decimal(r.operating_profit) == Decimal("350.00")
    # closing = 500 - (100*5 + 100) + 900 = 500 - 600 + 900 = 800
    assert Decimal(r.closing_cash) == Decimal("800.00")
    # No manufacturing-specific fields.
    assert r.material_shortage is None
    assert r.feasible_production is None


def test_service_scenario_full_run() -> None:
    r = run_scenario(
        {
            "industry": "service",
            "opening_cash": "1000.00",
            "billable_hours_capacity": "100",
            "planned_billable_utilization_pct": "0.80",
            "hourly_price": "150.00",
            "project_revenue": None,
            "labor_cost_per_hour": "60.00",
            "contractor_cost": "0",
            "project_expenses": "0",
            "operating_expenses": "200.00",
            "invoice_payment_delay_periods": 0,
            "horizon_months": 1,
        },
        "USD",
    )
    # billable hours = 80; revenue = 80 * 150 = 12000
    assert Decimal(r.revenue) == Decimal("12000.00")
    # labor cost = 4800
    assert Decimal(r.direct_costs) == Decimal("4800.00")
    # contribution = 7200
    assert Decimal(r.contribution_margin) == Decimal("7200.00")
    # operating = 7000
    assert Decimal(r.operating_profit) == Decimal("7000.00")
    # No manufacturing fields.
    assert r.units_sold is None


def test_unknown_industry_raises() -> None:
    with pytest.raises(ValueError, match="Unknown industry"):
        run_scenario({"industry": "mining", "opening_cash": "0"}, "USD")


def test_missing_required_input_raises() -> None:
    payload = _base_manufacturing_inputs()
    del payload["material_unit_cost"]
    with pytest.raises(Exception):
        run_scenario(payload, "USD")


def test_invalid_decimal_raises() -> None:
    payload = _base_manufacturing_inputs()
    payload["opening_cash"] = "not-a-number"
    with pytest.raises(ValueError):
        run_scenario(payload, "USD")


def test_horizon_above_max_rejected_by_schema() -> None:
    payload = _base_manufacturing_inputs()
    payload["horizon_months"] = 99
    with pytest.raises(Exception):
        run_scenario(payload, "USD")


def test_wholesale_and_food_use_inventory_inputs() -> None:
    # Same inventory shape; the runner just routes to run_inventory.
    for industry in ("wholesale", "food"):
        r = run_scenario(
            {
                "industry": industry,
                "opening_cash": "0",
                "opening_inventory_units": "0",
                "planned_purchase_units": "100",
                "purchase_unit_cost": "5.00",
                "selling_price": "10.00",
                "expected_units_sold": "80",
                "shrinkage_pct": "0",
                "operating_expenses": "0",
                "customer_payment_delay_periods": 0,
                "supplier_payment_delay_periods": 0,
                "horizon_months": 1,
            },
            "USD",
        )
        assert Decimal(r.revenue) == Decimal("800.00")
        assert Decimal(r.direct_costs) == Decimal("400.00")


def test_engine_version_is_stable() -> None:
    # The engine version is part of the contract. Bump deliberately, not by accident.
    r = run_scenario(_base_manufacturing_inputs(), "USD")
    assert r.engine_version == "0.1.0"
