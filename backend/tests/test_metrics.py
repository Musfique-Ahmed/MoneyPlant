"""Tests for core financial metrics and transaction-based cash/profit accounting."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.finance.metrics import (
    DIRECT_COST_CATEGORIES,
    OPEX_CATEGORIES,
    REVENUE_CATEGORIES,
    FinancialMetrics,
    Transaction,
    compute_metrics,
    is_direct_cost,
    is_opex,
    is_revenue,
)


def make_tx(
    *,
    tx_date: date,
    amount: str,
    direction: str,
    category: str,
    cash_flow_date: date | None = None,
    status: str | None = "paid",
) -> Transaction:
    return Transaction(
        tx_date=tx_date,
        cash_flow_date=cash_flow_date,
        amount=Decimal(amount),
        currency="USD",
        direction=direction,
        category=category,
        payment_status=status,
    )


def test_category_partition_disjoint() -> None:
    # The engine's classification is the source of truth; revenue categories must not
    # overlap with opex, etc. This guards against accidental re-categorisation.
    assert REVENUE_CATEGORIES.isdisjoint(OPEX_CATEGORIES)
    assert REVENUE_CATEGORIES.isdisjoint(DIRECT_COST_CATEGORIES)
    assert DIRECT_COST_CATEGORIES.isdisjoint(OPEX_CATEGORIES)


def test_is_revenue_opex_direct_cost_case_insensitive() -> None:
    assert is_revenue("Sales")
    assert is_direct_cost("MATERIALS")
    assert is_opex("Rent")
    assert not is_revenue("unknown_category")


def test_compute_metrics_zero_state() -> None:
    m = compute_metrics(
        transactions=[],
        opening_cash=Decimal("1000.00"),
        currency="USD",
        period_start=date(2026, 1, 1),
        period_end_exclusive=date(2026, 2, 1),
    )
    assert m.revenue == Decimal("0.00")
    assert m.direct_costs == Decimal("0.00")
    assert m.gross_profit == Decimal("0.00")
    assert m.operating_profit == Decimal("0.00")
    assert m.cash_inflows == Decimal("0.00")
    assert m.cash_outflows == Decimal("0.00")
    assert m.net_cash_movement == Decimal("0.00")
    assert m.closing_cash == Decimal("1000.00")
    assert m.transaction_count == 0
    # Margins on zero revenue are undefined.
    assert m.gross_margin() is None
    assert m.operating_margin() is None
    # Runway is undefined when there are no outflows.
    assert m.cash_runway_months() is None


def test_compute_metrics_full_period() -> None:
    txs = [
        make_tx(tx_date=date(2026, 1, 5), amount="1000.00", direction="inflow", category="sales"),
        make_tx(tx_date=date(2026, 1, 7), amount="400.00", direction="outflow", category="materials"),
        make_tx(tx_date=date(2026, 1, 10), amount="200.00", direction="outflow", category="rent"),
        make_tx(tx_date=date(2026, 1, 15), amount="150.00", direction="outflow", category="marketing"),
    ]
    m = compute_metrics(
        transactions=txs,
        opening_cash=Decimal("500.00"),
        currency="USD",
        period_start=date(2026, 1, 1),
        period_end_exclusive=date(2026, 2, 1),
    )
    assert m.revenue == Decimal("1000.00")
    assert m.direct_costs == Decimal("400.00")
    assert m.gross_profit == Decimal("600.00")
    assert m.operating_expenses == Decimal("350.00")  # 200 + 150
    assert m.operating_profit == Decimal("250.00")
    # All cash settled on tx_date.
    assert m.cash_inflows == Decimal("1000.00")
    assert m.cash_outflows == Decimal("750.00")
    assert m.net_cash_movement == Decimal("250.00")
    assert m.closing_cash == Decimal("750.00")
    assert m.gross_margin() == "0.6000"
    assert m.operating_margin() == "0.2500"
    # Runway = 750 / 750 = 1.00
    assert m.cash_runway_months() == "1.00"


def test_compute_metrics_defers_cash_to_cash_flow_date() -> None:
    # Revenue on the 5th, but customer pays on the 25th.
    txs = [
        make_tx(
            tx_date=date(2026, 1, 5),
            amount="1000.00",
            direction="inflow",
            category="sales",
            cash_flow_date=date(2026, 1, 25),
            status="pending",
        ),
    ]
    m = compute_metrics(
        transactions=txs,
        opening_cash=Decimal("0"),
        currency="USD",
        period_start=date(2026, 1, 1),
        period_end_exclusive=date(2026, 2, 1),
    )
    # Revenue is recognised at tx_date.
    assert m.revenue == Decimal("1000.00")
    # Cash hits the bank at cash_flow_date.
    assert m.cash_inflows == Decimal("1000.00")
    assert m.closing_cash == Decimal("1000.00")


def test_compute_metrics_excludes_cash_outside_period() -> None:
    txs = [
        make_tx(
            tx_date=date(2026, 1, 5),
            amount="1000.00",
            direction="inflow",
            category="sales",
            cash_flow_date=date(2026, 3, 1),  # next period
        ),
    ]
    m = compute_metrics(
        transactions=txs,
        opening_cash=Decimal("0"),
        currency="USD",
        period_start=date(2026, 1, 1),
        period_end_exclusive=date(2026, 2, 1),
    )
    # Revenue still counted in the period.
    assert m.revenue == Decimal("1000.00")
    # Cash NOT yet counted — it lands in March.
    assert m.cash_inflows == Decimal("0.00")
    assert m.closing_cash == Decimal("0.00")


def test_currency_mismatch_raises() -> None:
    txs = [
        make_tx(tx_date=date(2026, 1, 5), amount="100.00", direction="inflow", category="sales"),
    ]
    # Replace the currency on a transaction to force a mismatch.
    bad = Transaction(
        tx_date=date(2026, 1, 5),
        cash_flow_date=None,
        amount=Decimal("100.00"),
        currency="EUR",  # mixed
        direction="inflow",
        category="sales",
        payment_status="paid",
    )
    with pytest.raises(Exception):
        compute_metrics(
            transactions=[bad],
            opening_cash=Decimal("0"),
            currency="USD",
            period_start=date(2026, 1, 1),
            period_end_exclusive=date(2026, 2, 1),
        )


def test_cash_runway_uses_outflow_denominator() -> None:
    # Closing cash 600, cash outflows 200 → runway 3.00
    txs = [
        make_tx(tx_date=date(2026, 1, 5), amount="800.00", direction="inflow", category="sales"),
        make_tx(tx_date=date(2026, 1, 7), amount="200.00", direction="outflow", category="materials"),
    ]
    m = compute_metrics(
        transactions=txs,
        opening_cash=Decimal("0"),
        currency="USD",
        period_start=date(2026, 1, 1),
        period_end_exclusive=date(2026, 2, 1),
    )
    assert m.cash_runway_months() == "3.00"
    # explicit monthly_outflow overrides
    assert m.cash_runway_months(monthly_outflow=Decimal("300")) == "2.00"
