"""Invariant checks: closing_cash_equals_opening_plus_net_cash, etc."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.finance.invariants import (
    all_passed,
    assert_invariants,
    failures,
)


def test_closing_cash_invariant_passes_when_balanced() -> None:
    checks = assert_invariants(
        opening_cash=Decimal("100.00"),
        closing_cash=Decimal("150.00"),
        cash_inflows=Decimal("100.00"),
        cash_outflows=Decimal("50.00"),
        currency="USD",
    )
    closing = next(c for c in checks if c.name == "closing_cash_equals_opening_plus_net_cash")
    assert closing.passed


def test_closing_cash_invariant_fails_when_mismatched() -> None:
    checks = assert_invariants(
        opening_cash=Decimal("100.00"),
        closing_cash=Decimal("151.00"),  # off by one
        cash_inflows=Decimal("100.00"),
        cash_outflows=Decimal("50.00"),
        currency="USD",
    )
    closing = next(c for c in checks if c.name == "closing_cash_equals_opening_plus_net_cash")
    assert not closing.passed
    assert "151" in closing.detail


def test_units_sold_le_produced() -> None:
    checks = assert_invariants(
        opening_cash=Decimal("0"),
        closing_cash=Decimal("0"),
        cash_inflows=Decimal("0"),
        cash_outflows=Decimal("0"),
        currency="USD",
        units_sold=Decimal("50"),
        units_produced=Decimal("100"),
    )
    sold = next(c for c in checks if c.name == "units_sold_le_units_produced")
    assert sold.passed

    bad = assert_invariants(
        opening_cash=Decimal("0"),
        closing_cash=Decimal("0"),
        cash_inflows=Decimal("0"),
        cash_outflows=Decimal("0"),
        currency="USD",
        units_sold=Decimal("200"),
        units_produced=Decimal("100"),
    )
    sold_bad = next(c for c in bad if c.name == "units_sold_le_units_produced")
    assert not sold_bad.passed


def test_material_used_le_available() -> None:
    checks = assert_invariants(
        opening_cash=Decimal("0"),
        closing_cash=Decimal("0"),
        cash_inflows=Decimal("0"),
        cash_outflows=Decimal("0"),
        currency="USD",
        material_used=Decimal("80"),
        available_material=Decimal("100"),
    )
    m = next(c for c in checks if c.name == "material_used_le_available")
    assert m.passed


def test_feasible_production_le_capacity() -> None:
    checks = assert_invariants(
        opening_cash=Decimal("0"),
        closing_cash=Decimal("0"),
        cash_inflows=Decimal("0"),
        cash_outflows=Decimal("0"),
        currency="USD",
        feasible_production=Decimal("100"),
        production_capacity=Decimal("150"),
    )
    cap = next(c for c in checks if c.name == "feasible_production_le_capacity")
    assert cap.passed


def test_revenue_equals_units_sold_times_price() -> None:
    checks = assert_invariants(
        opening_cash=Decimal("0"),
        closing_cash=Decimal("0"),
        cash_inflows=Decimal("0"),
        cash_outflows=Decimal("0"),
        currency="USD",
        units_sold=Decimal("100"),
        selling_price=Decimal("20.00"),
        revenue=Decimal("2000.00"),
    )
    rev = next(c for c in checks if c.name == "revenue_equals_units_sold_times_price")
    assert rev.passed

    bad = assert_invariants(
        opening_cash=Decimal("0"),
        closing_cash=Decimal("0"),
        cash_inflows=Decimal("0"),
        cash_outflows=Decimal("0"),
        currency="USD",
        units_sold=Decimal("100"),
        selling_price=Decimal("20.00"),
        revenue=Decimal("1999.00"),
    )
    rev_bad = next(c for c in bad if c.name == "revenue_equals_units_sold_times_price")
    assert not rev_bad.passed


def test_all_passed_and_failures_helpers() -> None:
    checks = assert_invariants(
        opening_cash=Decimal("0"),
        closing_cash=Decimal("0"),
        cash_inflows=Decimal("0"),
        cash_outflows=Decimal("0"),
        currency="USD",
    )
    assert all_passed(checks)
    assert failures(checks) == []

    bad = assert_invariants(
        opening_cash=Decimal("100"),
        closing_cash=Decimal("200"),  # mismatch
        cash_inflows=Decimal("50"),
        cash_outflows=Decimal("50"),
        currency="USD",
    )
    assert not all_passed(bad)
    assert len(failures(bad)) == 1


def test_unknown_invariants_are_skipped() -> None:
    # Without manufacturing fields, the manufacturing-specific invariants should not be added.
    checks = assert_invariants(
        opening_cash=Decimal("0"),
        closing_cash=Decimal("0"),
        cash_inflows=Decimal("0"),
        cash_outflows=Decimal("0"),
        currency="USD",
    )
    names = {c.name for c in checks}
    assert "closing_cash_equals_opening_plus_net_cash" in names
    assert "units_sold_le_units_produced" not in names
    assert "material_used_le_available" not in names
