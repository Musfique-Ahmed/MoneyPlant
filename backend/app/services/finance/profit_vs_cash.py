"""Profit vs cash adjustments.

Explicit modelling of the distinction between profit recognition and cash
movement. Credit sales, supplier purchases, and unsold inventory are the
three big cases the engine handles explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.finance.metrics import Transaction
from app.services.finance.money import (
    ZERO,
    add,
    format_money,
    parse_money_str,
    sub,
)


@dataclass(frozen=True)
class ProfitCashReconciliation:
    """A side-by-side summary of profit and cash for a period."""

    currency: str
    revenue: Decimal
    cogs: Decimal
    opex: Decimal
    operating_profit: Decimal
    cash_inflows: Decimal
    cash_outflows: Decimal
    net_cash_movement: Decimal
    notes: list[str]


def reconcile_profit_and_cash(
    transactions: list[Transaction],
    period_start: date,
    period_end_exclusive: date,
    currency: str,
    opening_cash: Decimal,
) -> ProfitCashReconciliation:
    """Compute profit and cash for a period with explicit notes on the reconciliation.

    This is the canonical helper for the "I made a profit but I'm short on
    cash" question. The notes list documents the assumptions and any
    adjustments that were applied.
    """
    notes: list[str] = []
    revenue = ZERO
    cogs = ZERO
    opex = ZERO
    cash_inflows = ZERO
    cash_outflows = ZERO

    for t in transactions:
        if period_start <= t.tx_date < period_end_exclusive:
            if t.direction == "inflow":
                revenue = add(revenue, t.amount, currency)
            else:
                # Split between COGS (categories flagged as direct) and opex.
                # The categorisation comes from :mod:`metrics`.
                from app.services.finance.metrics import is_direct_cost, is_opex

                if is_direct_cost(t.category):
                    cogs = add(cogs, t.amount, currency)
                elif is_opex(t.category):
                    opex = add(opex, t.amount, currency)
        # Cash side: use cash_flow_date (default = tx_date)
        cd = t.cash_flow_date or t.tx_date
        if period_start <= cd < period_end_exclusive:
            if t.direction == "inflow":
                cash_inflows = add(cash_inflows, t.amount, currency)
            else:
                cash_outflows = add(cash_outflows, t.amount, currency)

    # Pending credit sales: revenue recognised at tx_date, cash only later.
    pending_credit = sum(
        (t.amount for t in transactions
         if t.direction == "inflow"
         and (t.payment_status or "").lower() == "pending"
         and period_start <= t.tx_date < period_end_exclusive),
        ZERO,
    )
    if pending_credit > ZERO:
        notes.append(
            f"{format_money(pending_credit, currency)} of revenue recognised this period is "
            f"uncollected credit sales (payment_status=pending). Cash impact will arrive later."
        )

    # Inventory purchases: cash out now, expense recognised when consumed.
    # We don't have a consumption model here; flag the situation for the user.
    inventory_outflow = sum(
        (t.amount for t in transactions
         if t.direction == "outflow"
         and t.category.lower() in {"materials", "cogs", "production_supplies"}
         and period_start <= (t.cash_flow_date or t.tx_date) < period_end_exclusive),
        ZERO,
    )
    if inventory_outflow > ZERO:
        notes.append(
            f"{format_money(inventory_outflow, currency)} of supplier cash outflow is for "
            f"inventory or materials. Some of this may remain on the balance sheet as inventory."
        )

    operating_profit = sub(sub(revenue, cogs, currency), opex, currency)
    net_cash = sub(cash_inflows, cash_outflows, currency)

    if operating_profit > ZERO and net_cash < ZERO:
        notes.append(
            "Operating profit is positive but net cash is negative — "
            "this typically means credit sales or inventory build-up are tying up cash."
        )
    elif operating_profit < ZERO and net_cash > ZERO:
        notes.append(
            "Operating profit is negative but net cash is positive — "
            "check whether the cash came from non-operating sources or deferred payments."
        )

    closing_cash = add(opening_cash, net_cash, currency)
    notes.append(f"Closing cash for the period: {format_money(closing_cash, currency)}.")

    return ProfitCashReconciliation(
        currency=currency,
        revenue=revenue,
        cogs=cogs,
        opex=opex,
        operating_profit=operating_profit,
        cash_inflows=cash_inflows,
        cash_outflows=cash_outflows,
        net_cash_movement=net_cash,
        notes=notes,
    )


__all__ = ["ProfitCashReconciliation", "reconcile_profit_and_cash"]