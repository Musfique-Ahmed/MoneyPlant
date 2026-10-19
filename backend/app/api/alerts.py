"""Cash-flow alerts endpoint.

The endpoint buckets the business's persisted transactions by month using
``MonthlyPeriod`` (the same half-open convention the financial engine
uses), feeds the per-month closing cash into the pure ``app.engine.alerts``
module, and returns a deterministic list of alerts. The LLM and Laya
never participate in this calculation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engine.alerts import (
    Alert,
    AlertConfig,
    MonthlyCashPoint,
    evaluate_alerts,
)
from app.models.business import Business
from app.models.transaction import Transaction
from app.schemas.alerts import (
    AlertConfigRead,
    AlertRead,
    AlertsResponse,
    MonthlyCashPointRead,
)
from app.schemas.money import Currency
from app.services.finance.metrics import (
    DIRECT_COST_CATEGORIES,
    OPEX_CATEGORIES,
    Transaction as EngineTx,
    compute_metrics,
)
from app.services.finance.money import (
    ZERO,
    format_money,
    quantize,
    safe_div_str,
)
from app.services.finance.periods import MonthlyPeriod, months_between

router = APIRouter(prefix="/businesses", tags=["alerts"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_engine_tx(t: Transaction) -> EngineTx:
    """Map the SQLAlchemy row to the engine's typed Transaction."""
    return EngineTx(
        tx_date=t.tx_date,
        cash_flow_date=t.cash_flow_date,
        amount=Decimal(t.amount),
        currency=t.currency,
        direction=t.direction,
        category=t.category,
        payment_status=t.payment_status,
    )


def _bucket_by_month(rows: Iterable[Transaction]) -> list[MonthlyPeriod]:
    """Return the ordered list of MonthlyPeriod buckets that contain ``cash_flow_date``.

    We use ``cash_flow_date`` (not ``tx_date``) so that pending credit
    sales and supplier-payment-delayed purchases land in the bucket where
    the cash actually moves — that's what the alerts engine cares about.
    """
    buckets: dict[str, MonthlyPeriod] = {}
    for r in rows:
        cd = r.cash_flow_date or r.tx_date
        key = f"{cd.year}-{cd.month:02d}"
        if key not in buckets:
            buckets[key] = MonthlyPeriod.containing(cd)
    if not buckets:
        return []
    return sorted(buckets.values(), key=lambda p: p.start)


def _window_totals(
    rows: list[Transaction],
    period: MonthlyPeriod,
    currency: str,
) -> tuple[Decimal, Decimal, Decimal]:
    """Sum revenue, cogs, opex for a single monthly bucket using the engine's category sets."""
    revenue = ZERO
    cogs = ZERO
    opex = ZERO
    for t in rows:
        if not period.contains(t.cash_flow_date or t.tx_date):
            continue
        amt = Decimal(t.amount)
        if t.direction == "inflow":
            revenue = quantize(revenue + amt, currency)
        else:
            cat = (t.category or "").lower()
            if cat in DIRECT_COST_CATEGORIES:
                cogs = quantize(cogs + amt, currency)
            elif cat in OPEX_CATEGORIES:
                opex = quantize(opex + amt, currency)
    return revenue, cogs, opex


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/{business_id}/alerts", response_model=AlertsResponse)
def get_business_alerts(
    business_id: str,
    db: Session = Depends(get_db),
) -> AlertsResponse:
    """Compute deterministic cash-flow alerts for a business.

    The trajectory is the per-month closing cash built from the persisted
    transactions (cash flows land in the bucket of their ``cash_flow_date``).
    The opening cash for month 1 is zero unless the user has supplied an
    opening balance elsewhere; this is documented in the response note.

    All math runs in ``decimal.Decimal``. The LLM and Laya never touch this.
    """
    business = db.get(Business, business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="business_not_found")

    currency = Currency(business.currency)
    cfg = AlertConfig()
    config_read = AlertConfigRead(
        low_buffer_months=str(cfg.low_buffer_months),
        short_runway_warning_months=str(cfg.short_runway_warning_months),
        short_runway_critical_months=str(cfg.short_runway_critical_months),
        sharp_drop_pct=str(cfg.sharp_drop_pct),
    )

    rows = (
        db.query(Transaction)
        .filter(Transaction.business_id == business_id)
        .order_by(Transaction.tx_date.asc())
        .all()
    )

    if not rows:
        return AlertsResponse(
            business_id=business.id,
            currency=currency,
            horizon_months=0,
            runway_months=None,
            operating_profit=format_money(ZERO, business.currency),
            monthly_cash=[],
            config=config_read,
            alerts=[],
            source="transactions-derived",
            note=(
                "No transactions yet. Import a CSV first; the alerts engine "
                "needs at least one period of activity to produce a trajectory."
            ),
        )

    buckets = _bucket_by_month(rows)
    points: list[MonthlyCashPoint] = []
    total_revenue = ZERO
    total_cogs = ZERO
    total_opex = ZERO

    opening_running = ZERO  # Documented in the response note.

    for idx, period in enumerate(buckets, start=1):
        txs_in_bucket = [
            _to_engine_tx(t)
            for t in rows
            if period.contains(t.cash_flow_date or t.tx_date)
        ]
        metrics = compute_metrics(
            txs_in_bucket,
            opening_cash=opening_running,
            currency=business.currency,
            period_start=period.start,
            period_end_exclusive=period.end_exclusive,
        )
        net = metrics.cash_inflows - metrics.cash_outflows
        closing = opening_running + net

        points.append(
            MonthlyCashPoint(
                month_index=idx,
                opening_cash=quantize(opening_running, business.currency),
                net_cash_movement=quantize(net, business.currency),
                closing_cash=quantize(closing, business.currency),
            )
        )

        rev_p, cogs_p, opex_p = _window_totals(rows, period, business.currency)
        total_revenue = quantize(total_revenue + rev_p, business.currency)
        total_cogs = quantize(total_cogs + cogs_p, business.currency)
        total_opex = quantize(total_opex + opex_p, business.currency)

        opening_running = closing

    operating_profit = quantize(total_revenue - total_cogs - total_opex, business.currency)

    # Runway: closing cash / avg monthly outflow, with explicit guard for zero.
    outflow_months = [-(p.net_cash_movement) for p in points if p.net_cash_movement < ZERO]
    runway_str: str | None = None
    if outflow_months and points:
        avg_outflow = sum(outflow_months, ZERO) / Decimal(len(outflow_months))
        closing_final = points[-1].closing_cash
        if avg_outflow > ZERO and closing_final > ZERO:
            runway_str = safe_div_str(closing_final, avg_outflow, business.currency, places=4)

    triggered: list[Alert] = evaluate_alerts(
        points=points,
        runway_months=(Decimal(runway_str) if runway_str is not None else None),
        operating_profit=operating_profit,
        currency=business.currency,
        config=cfg,
    )

    monthly_read = [
        MonthlyCashPointRead(
            month_index=p.month_index,
            opening_cash=str(p.opening_cash),
            net_cash_movement=str(p.net_cash_movement),
            closing_cash=str(p.closing_cash),
        )
        for p in points
    ]
    alert_read = [
        AlertRead(
            code=a.code,
            severity=a.severity,
            month=a.month,
            message=a.message,
            evidence=a.evidence,
        )
        for a in triggered
    ]

    horizon_months = max(1, months_between(buckets[0].start, buckets[-1].end_exclusive))

    return AlertsResponse(
        business_id=business.id,
        currency=currency,
        horizon_months=horizon_months,
        runway_months=runway_str,
        operating_profit=format_money(operating_profit, business.currency),
        monthly_cash=monthly_read,
        config=config_read,
        alerts=alert_read,
        source="transactions-derived",
        note=(
            "Alerts are computed deterministically from the imported transactions "
            "by the engine. The LLM and Laya do not participate in this calculation. "
            "Opening cash for the first bucket is treated as 0 unless the business "
            "settings supply a balance — use a scenario to project from a known opening."
        ),
    )


__all__ = ["router"]