"""Transaction list + financial summary endpoints.

The summary is the dashboard's authoritative read; it is computed by the
deterministic engine over the persisted transactions, not by the LLM.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.business import Business
from app.models.transaction import Transaction
from app.schemas.business import BusinessRead, Industry
from app.schemas.money import Currency
from app.schemas.transaction import (
    Direction,
    FinancialSummary,
    PaymentStatus,
    TransactionList,
    TransactionRead,
)
from app.services.finance.money import format_money, safe_div_str
from app.services.finance.periods import months_between

router = APIRouter(
    prefix="",  # mounted under /api, so we get /api/transactions directly
    tags=["transactions"],
)


# --- helpers --------------------------------------------------------------


def _to_read(t: Transaction) -> TransactionRead:
    return TransactionRead(
        id=t.id,
        business_id=t.business_id,
        tx_date=t.tx_date,
        cash_flow_date=t.cash_flow_date,
        description=t.description,
        amount=str(t.amount),
        currency=Currency(t.currency),
        direction=Direction(t.direction),
        category=t.category,
        payment_status=PaymentStatus(t.payment_status) if t.payment_status else None,
        customer_or_supplier=t.customer_or_supplier,
        source_file=t.source_file,
        source_sheet=t.source_sheet,
        source_row=t.source_row,
        import_job_id=t.import_job_id,
        created_at=t.created_at,
    )


def _business_to_read(b: Business) -> BusinessRead:
    return BusinessRead(
        id=b.id,
        name=b.name,
        industry=Industry(b.industry),
        currency=Currency(b.currency),
        fiscal_year_start_month=b.fiscal_year_start_month,
        locale=b.locale,
        min_cash_reserve=str(b.min_cash_reserve),
        target_operating_margin=str(b.target_operating_margin),
        max_unsold_inventory_exposure_pct=str(b.max_unsold_inventory_exposure_pct),
        created_at=b.created_at,
        updated_at=b.updated_at,
    )


# --- routes ---------------------------------------------------------------


@router.get("/transactions", response_model=TransactionList)
def list_transactions(
    business_id: str = Query(...),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    category: str | None = Query(None),
    direction: Direction | None = Query(None),
    db: Session = Depends(get_db),
) -> TransactionList:
    q = db.query(Transaction).filter(Transaction.business_id == business_id)
    if category is not None:
        q = q.filter(Transaction.category == category)
    if direction is not None:
        q = q.filter(Transaction.direction == direction.value)
    total = q.count()
    rows = q.order_by(Transaction.tx_date.desc(), Transaction.created_at.desc()).offset(offset).limit(limit).all()
    return TransactionList(items=[_to_read(t) for t in rows], total=total)


@router.get("/transactions/categories", response_model=list[str])
def list_categories(business_id: str = Query(...), db: Session = Depends(get_db)) -> list[str]:
    rows = (
        db.query(Transaction.category)
        .filter(Transaction.business_id == business_id)
        .distinct()
        .all()
    )
    return sorted([r[0] for r in rows if r[0]])


@router.get("/financial-summary", response_model=FinancialSummary)
def financial_summary(
    business_id: str = Query(...),
    period_start: date | None = Query(
        None, description="Start of the period (inclusive). Defaults to the earliest tx."
    ),
    period_end_exclusive: date | None = Query(
        None, description="End of the period (exclusive). Defaults to the latest tx + 1 day."
    ),
    db: Session = Depends(get_db),
) -> FinancialSummary:
    """Compute the dashboard's authoritative summary from the persisted transactions.

    The summary is fully deterministic. The LLM is never used here.
    """
    business = db.get(Business, business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="business_not_found")
    biz = _business_to_read(business)
    currency = biz.currency
    q = db.query(Transaction).filter(Transaction.business_id == business_id)
    rows = q.order_by(Transaction.tx_date.asc()).all()
    if not rows:
        today = date.today()
        empty = _zero_summary(biz, today, today)
        empty.is_empty = True
        return empty

    earliest = rows[0].tx_date
    latest = rows[-1].tx_date
    if period_start is None:
        period_start = earliest
    if period_end_exclusive is None:
        period_end_exclusive = latest + timedelta(days=1)

    rows_in_window = [r for r in rows if period_start <= r.tx_date < period_end_exclusive]

    revenue = Decimal("0")
    cogs = Decimal("0")
    opex = Decimal("0")
    cash_inflows = Decimal("0")
    cash_outflows = Decimal("0")
    has_revenue = False
    has_cogs = False
    has_opex = False
    has_inflow = False
    has_outflow = False
    min_projected = Decimal("0")
    opening = Decimal("0")  # Authoritative engine treats opening as user-supplied
    for r in rows_in_window:
        amt = Decimal(r.amount)
        if r.direction == Direction.INFLOW.value:
            revenue += amt
            cash_inflows += amt
            has_revenue = True
            has_inflow = True
        else:
            cat = (r.category or "").lower()
            if cat in {"materials", "raw materials", "inventory", "cogs", "cost of goods sold"}:
                cogs += amt
                has_cogs = True
            elif cat in {"labor", "wages", "contractor", "contractor cost"}:
                cogs += amt
                has_cogs = True
            else:
                opex += amt
                has_opex = True
            cash_outflows += amt
            has_outflow = True

    gross_profit = revenue - cogs
    operating_profit = gross_profit - opex
    net = cash_inflows - cash_outflows
    closing = opening + net
    # We have no real period-by-period schedule from transactions; for the
    # dashboard we treat the minimum projected cash as the opening for now
    # and expose a clear warning that runway needs a scenario.
    min_projected = min(opening, closing)
    runway = None
    if cash_outflows > 0 and closing > 0:
        # Cheap, deterministic estimate: closing cash / avg monthly outflows.
        months = max(1, months_between(period_start, period_end_exclusive))
        avg_monthly = cash_outflows / Decimal(months)
        if avg_monthly > 0:
            runway = format_money(closing / avg_monthly, currency)

    coverage: dict[str, bool] = {
        "revenue": has_revenue,
        "direct_costs": has_cogs,
        "opex": has_opex,
        "cash_inflows": has_inflow,
        "cash_outflows": has_outflow,
    }
    warnings: list[str] = []
    if not has_inflow:
        warnings.append("No inflow transactions in the selected window.")
    if not has_outflow:
        warnings.append("No outflow transactions in the selected window.")
    if runway is None:
        warnings.append(
            "Cash runway is unavailable from raw transactions alone. "
            "Run a scenario to project the cash schedule month-by-month."
        )

    return FinancialSummary(
        business_id=business.id,
        currency=currency,
        period_start=period_start,
        period_end_exclusive=period_end_exclusive,
        revenue=format_money(revenue, currency),
        direct_costs=format_money(cogs, currency),
        gross_profit=format_money(gross_profit, currency),
        gross_margin=safe_div_str(gross_profit, revenue, currency, places=4),
        operating_expenses=format_money(opex, currency),
        operating_profit=format_money(operating_profit, currency),
        operating_margin=safe_div_str(operating_profit, revenue, currency, places=4),
        cash_inflows=format_money(cash_inflows, currency),
        cash_outflows=format_money(cash_outflows, currency),
        net_cash_movement=format_money(net, currency),
        opening_cash=format_money(opening, currency),
        closing_cash=format_money(closing, currency),
        minimum_projected_cash=format_money(min_projected, currency),
        cash_runway_months=runway,
        transaction_count=len(rows_in_window),
        data_coverage=coverage,
        warnings=warnings,
        is_empty=False,
    )


def _zero_summary(biz: BusinessRead, start: date, end: date) -> FinancialSummary:
    z = "0"
    return FinancialSummary(
        business_id=biz.id,
        currency=biz.currency,
        period_start=start,
        period_end_exclusive=end,
        revenue=z,
        direct_costs=z,
        gross_profit=z,
        gross_margin=None,
        operating_expenses=z,
        operating_profit=z,
        operating_margin=None,
        cash_inflows=z,
        cash_outflows=z,
        net_cash_movement=z,
        opening_cash=z,
        closing_cash=z,
        minimum_projected_cash=z,
        cash_runway_months=None,
        transaction_count=0,
        data_coverage={},
        warnings=[],
        is_empty=False,
    )


__all__ = ["router"]
