"""Core financial metrics.

All functions are pure. Inputs are lists of typed transaction dicts (the
adapter layer normalises source data into this shape). Currency is fixed
per call; mixing currencies raises :class:`CurrencyMismatch`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.finance.money import (
    ZERO,
    add,
    format_money,
    format_quantized,
    parse_money_str,
    quantize,
    safe_div_str,
    same_currency,
    sub,
)


@dataclass(frozen=True)
class Transaction:
    """The minimal typed shape the engine operates on. Adapters normalise raw rows to this."""

    tx_date: date
    cash_flow_date: date | None  # None means cash on tx_date
    amount: Decimal  # always positive
    currency: str
    direction: str  # "inflow" or "outflow"
    category: str
    payment_status: str | None  # "paid", "pending", "partial", or None


def _cash_date(t: Transaction) -> date:
    return t.cash_flow_date or t.tx_date


# Categories the engine treats as revenue, direct cost, or opex.
REVENUE_CATEGORIES: frozenset[str] = frozenset(
    {"sales", "revenue", "service_revenue", "product_revenue", "subscription_revenue"}
)
DIRECT_COST_CATEGORIES: frozenset[str] = frozenset(
    {"materials", "cogs", "direct_labor", "freight_in", "production_supplies", "packaging", "subcontractor"}
)
OPEX_CATEGORIES: frozenset[str] = frozenset(
    {"rent", "salaries", "utilities", "marketing", "office", "admin", "insurance", "travel", "professional_fees"}
)


def is_revenue(category: str) -> bool:
    return category.lower() in REVENUE_CATEGORIES


def is_direct_cost(category: str) -> bool:
    return category.lower() in DIRECT_COST_CATEGORIES


def is_opex(category: str) -> bool:
    return category.lower() in OPEX_CATEGORIES


@dataclass(frozen=True)
class FinancialMetrics:
    currency: str
    revenue: Decimal
    direct_costs: Decimal
    gross_profit: Decimal
    operating_expenses: Decimal
    operating_profit: Decimal
    cash_inflows: Decimal
    cash_outflows: Decimal
    net_cash_movement: Decimal
    opening_cash: Decimal
    closing_cash: Decimal
    transaction_count: int

    def gross_margin(self) -> str | None:
        return safe_div_str(self.gross_profit, self.revenue, self.currency, places=4)

    def operating_margin(self) -> str | None:
        return safe_div_str(self.operating_profit, self.revenue, self.currency, places=4)

    def cash_runway_months(self, monthly_outflow: Decimal | None = None) -> str | None:
        """Runway in months = closing_cash / avg monthly outflow. None when outflow is 0."""
        denom = monthly_outflow if monthly_outflow is not None else self.cash_outflows
        if denom == ZERO:
            return None
        return format_quantized(self.closing_cash / denom, self.currency)


def compute_metrics(
    transactions: list[Transaction],
    opening_cash: Decimal,
    currency: str,
    period_start: date,
    period_end_exclusive: date,
) -> FinancialMetrics:
    """Compute headline metrics for a period.

    The caller is responsible for pre-filtering transactions to the period.
    ``opening_cash`` is the cash position at ``period_start``; closing cash
    is ``opening + net_cash_movement`` over the period.
    """
    revenue = ZERO
    direct_costs = ZERO
    opex = ZERO
    cash_inflows = ZERO
    cash_outflows = ZERO
    n = 0
    for t in transactions:
        if t.currency.upper() != currency.upper():
            same_currency(t.currency, currency)
        n += 1
        if t.direction == "inflow":
            if is_revenue(t.category):
                revenue = add(revenue, t.amount, currency)
            # All inflows add to cash when cash_flow_date is in period.
            cd = _cash_date(t)
            if period_start <= cd < period_end_exclusive:
                cash_inflows = add(cash_inflows, t.amount, currency)
        elif t.direction == "outflow":
            if is_direct_cost(t.category):
                direct_costs = add(direct_costs, t.amount, currency)
            elif is_opex(t.category):
                opex = add(opex, t.amount, currency)
            # Outflows subtract from cash at their cash_flow_date.
            cd = _cash_date(t)
            if period_start <= cd < period_end_exclusive:
                cash_outflows = add(cash_outflows, t.amount, currency)

    gross_profit = sub(revenue, direct_costs, currency)
    operating_profit = sub(gross_profit, opex, currency)
    net_cash = sub(cash_inflows, cash_outflows, currency)
    closing_cash = add(opening_cash, net_cash, currency)
    return FinancialMetrics(
        currency=currency,
        revenue=revenue,
        direct_costs=direct_costs,
        gross_profit=gross_profit,
        operating_expenses=opex,
        operating_profit=operating_profit,
        cash_inflows=cash_inflows,
        cash_outflows=cash_outflows,
        net_cash_movement=net_cash,
        opening_cash=opening_cash,
        closing_cash=closing_cash,
        transaction_count=n,
    )


def format_metrics_summary(m: FinancialMetrics) -> dict[str, str | None]:
    """Serialise a :class:`FinancialMetrics` to a dict of formatted strings for the API."""

    def fmt(d: Decimal) -> str:
        return format_money(d, m.currency)

    return {
        "currency": m.currency,
        "revenue": fmt(m.revenue),
        "direct_costs": fmt(m.direct_costs),
        "gross_profit": fmt(m.gross_profit),
        "gross_margin": m.gross_margin(),
        "operating_expenses": fmt(m.operating_expenses),
        "operating_profit": fmt(m.operating_profit),
        "operating_margin": m.operating_margin(),
        "cash_inflows": fmt(m.cash_inflows),
        "cash_outflows": fmt(m.cash_outflows),
        "net_cash_movement": fmt(m.net_cash_movement),
        "opening_cash": fmt(m.opening_cash),
        "closing_cash": fmt(m.closing_cash),
        "cash_runway_months": m.cash_runway_months(),
    }


def parse_opening_cash(value: str | Decimal, currency: str) -> Decimal:
    return parse_money_str(value, currency)


def quantize_period(value: Decimal, currency: str) -> Decimal:
    return quantize(value, currency)


__all__ = [
    "Transaction",
    "REVENUE_CATEGORIES",
    "DIRECT_COST_CATEGORIES",
    "OPEX_CATEGORIES",
    "is_revenue",
    "is_direct_cost",
    "is_opex",
    "FinancialMetrics",
    "compute_metrics",
    "format_metrics_summary",
    "parse_opening_cash",
]