"""Dashboard-insights endpoint.

Aggregates the business's persisted transactions into per-month metrics
and category totals, runs the deterministic insights engine, and returns
a list of :class:`DashboardVisual` payloads for the frontend. The LLM
and Laya are not involved at any point.

The endpoint accepts the same ``period_start`` / ``period_end_exclusive``
filters as the existing ``/api/financial-summary`` endpoint. There is
no industry filter — the engine is industry-agnostic.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engine.alerts import (
    AlertConfig,
    evaluate_alerts,
)
from app.insights.engine import (
    CategoryTotal,
    DashboardInputs,
    MonthlyAggregate,
    SensitivitySlice,
    build_dashboard_insights,
    compute_aggregates,
)
from app.models.business import Business
from app.models.transaction import Transaction
from app.schemas.insights import DashboardInsightsResponse, DashboardVisual
from app.services.finance.metrics import (
    DIRECT_COST_CATEGORIES,
    OPEX_CATEGORIES,
    Transaction as EngineTx,
    compute_metrics,
)
from app.services.finance.money import ZERO, format_money, quantize, safe_div_str
from app.services.finance.periods import MonthlyPeriod, months_between

router = APIRouter(prefix="/businesses", tags=["insights"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_engine_tx(t: Transaction) -> EngineTx:
    return EngineTx(
        tx_date=t.tx_date,
        cash_flow_date=t.cash_flow_date,
        amount=Decimal(t.amount),
        currency=t.currency,
        direction=t.direction,
        category=t.category,
        payment_status=t.payment_status,
    )


def _bucket_by_month(rows: list[Transaction]) -> list[MonthlyPeriod]:
    buckets: dict[str, MonthlyPeriod] = {}
    for r in rows:
        cd = r.cash_flow_date or r.tx_date
        key = f"{cd.year}-{cd.month:02d}"
        if key not in buckets:
            buckets[key] = MonthlyPeriod.containing(cd)
    return sorted(buckets.values(), key=lambda p: p.start)


def _category_for_engine(cat: str) -> str:
    """Map a transaction's category to one of: revenue / direct_cost / opex / other."""
    c = (cat or "").lower()
    if c in {
        "sales", "revenue", "service_revenue", "product_revenue", "subscription_revenue",
    }:
        return "revenue"
    if c in DIRECT_COST_CATEGORIES:
        return "direct_cost"
    if c in OPEX_CATEGORIES:
        return "opex"
    return "other"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/{business_id}/dashboard-insights", response_model=DashboardInsightsResponse)
def get_dashboard_insights(
    business_id: str,
    db: Session = Depends(get_db),
    period_start: date | None = Query(
        None, description="Start of the period (inclusive). Defaults to the earliest tx."
    ),
    period_end_exclusive: date | None = Query(
        None, description="End of the period (exclusive). Defaults to the latest tx + 1 day."
    ),
) -> DashboardInsightsResponse:
    """Compute deterministic dashboard insights for a business.

    The endpoint returns a list of :class:`DashboardVisual` payloads that
    the frontend pairs with charts. Every quoted number is recomputed
    from the input, and the API layer never re-formats anything.
    """
    business = db.get(Business, business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="business_not_found")
    currency = business.currency

    rows = (
        db.query(Transaction)
        .filter(Transaction.business_id == business_id)
        .order_by(Transaction.tx_date.asc())
        .all()
    )
    if not rows:
        today = date.today()
        empty = build_dashboard_insights(
            compute_aggregates(
                currency=currency,
                monthly=[],
                category_breakdown=[],
                alerts=[],
            )
        )
        return DashboardInsightsResponse(
            business_id=business.id,
            currency=currency,
            period_start=period_start.isoformat() if period_start else today.isoformat(),
            period_end_exclusive=(
                period_end_exclusive.isoformat() if period_end_exclusive else today.isoformat()
            ),
            calculation_timestamp=datetime.now(timezone.utc).isoformat(),
            visuals=empty,
            alerts_count=0,
            financing_counts={},
            summary={
                "is_empty": True,
                "revenue": "0",
                "total_costs": "0",
                "operating_profit": "0",
                "closing_cash": "0",
            },
        )

    earliest = rows[0].tx_date
    latest = rows[-1].tx_date
    if period_start is None:
        period_start = earliest
    if period_end_exclusive is None or period_end_exclusive <= period_start:
        period_end_exclusive = latest + timedelta(days=1)

    rows_in_window = [r for r in rows if period_start <= r.tx_date < period_end_exclusive]
    if not rows_in_window:
        empty = build_dashboard_insights(
            compute_aggregates(currency=currency, monthly=[], category_breakdown=[], alerts=[])
        )
        return DashboardInsightsResponse(
            business_id=business.id,
            currency=currency,
            period_start=period_start.isoformat(),
            period_end_exclusive=period_end_exclusive.isoformat(),
            calculation_timestamp=datetime.now(timezone.utc).isoformat(),
            visuals=empty,
            alerts_count=0,
            financing_counts={},
            summary={
                "is_empty": True,
                "revenue": "0",
                "total_costs": "0",
                "operating_profit": "0",
                "closing_cash": "0",
            },
        )

    # --- Per-month bucketing -----------------------------------------------
    buckets = _bucket_by_month(rows_in_window)
    monthly: list[MonthlyAggregate] = []
    category_totals: dict[str, Decimal] = {}
    total_revenue = ZERO
    total_direct = ZERO
    total_opex = ZERO
    total_cash_in = ZERO
    total_cash_out = ZERO
    opening_running = ZERO

    for idx, period in enumerate(buckets, start=1):
        txs_in_bucket = [
            _to_engine_tx(t)
            for t in rows_in_window
            if period.contains(t.cash_flow_date or t.tx_date)
        ]
        metrics = compute_metrics(
            txs_in_bucket,
            opening_cash=opening_running,
            currency=currency,
            period_start=period.start,
            period_end_exclusive=period.end_exclusive,
        )

        # Per-category costs inside this bucket.
        cat_totals: dict[str, Decimal] = {}
        for t in txs_in_bucket:
            if t.direction != "outflow":
                continue
            kind = _category_for_engine(t.category)
            if kind in {"direct_cost", "opex"}:
                cat_totals[t.category] = quantize(
                    cat_totals.get(t.category, ZERO) + t.amount, currency
                )
                category_totals[t.category] = quantize(
                    category_totals.get(t.category, ZERO) + t.amount, currency
                )

        net = metrics.cash_inflows - metrics.cash_outflows
        closing = opening_running + net

        monthly.append(
            MonthlyAggregate(
                month_index=idx,
                month_label=period.label(),
                revenue=metrics.revenue,
                direct_costs=metrics.direct_costs,
                operating_expenses=metrics.operating_expenses,
                operating_profit=metrics.operating_profit,
                gross_profit=metrics.gross_profit,
                cash_inflows=metrics.cash_inflows,
                cash_outflows=metrics.cash_outflows,
                net_cash_movement=net,
                opening_cash=opening_running,
                closing_cash=closing,
                cost_by_category=cat_totals,
            )
        )
        total_revenue = quantize(total_revenue + metrics.revenue, currency)
        total_direct = quantize(total_direct + metrics.direct_costs, currency)
        total_opex = quantize(total_opex + metrics.operating_expenses, currency)
        total_cash_in = quantize(total_cash_in + metrics.cash_inflows, currency)
        total_cash_out = quantize(total_cash_out + metrics.cash_outflows, currency)
        opening_running = closing

    # --- Alerts over the same trajectory -----------------------------------
    cfg = AlertConfig()
    from app.engine.alerts import MonthlyCashPoint
    points = [
        MonthlyCashPoint(
            month_index=m.month_index,
            opening_cash=m.opening_cash,
            net_cash_movement=m.net_cash_movement,
            closing_cash=m.closing_cash,
        )
        for m in monthly
    ]
    closing_final = monthly[-1].closing_cash if monthly else ZERO
    outflow_months = [-(m.net_cash_movement) for m in monthly if m.net_cash_movement < ZERO]
    runway_months: Decimal | None = None
    if outflow_months and closing_final > ZERO:
        avg_outflow = sum(outflow_months, ZERO) / Decimal(len(outflow_months))
        if avg_outflow > ZERO:
            runway_months = quantize(closing_final / avg_outflow, currency)

    triggered = evaluate_alerts(
        points=points,
        runway_months=runway_months,
        operating_profit=quantize(
            total_revenue - total_direct - total_opex, currency
        ),
        currency=currency,
        config=cfg,
    )

    # --- Category breakdown (sorted descending) ----------------------------
    category_breakdown = [
        CategoryTotal(category=k, amount=v)
        for k, v in category_totals.items()
    ]

    # --- Sensitivity on the observed period --------------------------------
    # Deterministic, observed-period one-at-a-time sensitivity:
    # scale monthly inflows (revenue proxy) and outflows (cost proxy) by ±25% / ±10%
    # independently, recompute running closing cash, and report the cumulative delta.
    sensitivity_slices: list[SensitivitySlice] = []
    multipliers = [Decimal("-0.25"), Decimal("-0.10"), Decimal("0"), Decimal("0.10"), Decimal("0.25")]
    multiplier_labels = ["-0.25", "-0.10", "0", "0.10", "0.25"]
    sensitivity_axes = [
        ("revenue", "inflows"),
        ("costs", "outflows"),
    ]
    for axis_label, kind in sensitivity_axes:
        points_by_mult: list[Decimal] = []
        for mult in multipliers:
            running = ZERO
            for mm in monthly:
                if kind == "inflows":
                    net = quantize(
                        mm.cash_inflows * (Decimal(1) + mult) + mm.cash_outflows,
                        currency,
                    )
                else:
                    net = quantize(
                        mm.cash_inflows + mm.cash_outflows * (Decimal(1) + mult),
                        currency,
                    )
                running = quantize(running + net, currency)
            points_by_mult.append(running)
        if any(p != ZERO for p in points_by_mult):
            baseline = points_by_mult[2]  # multiplier 0
            best = max(points_by_mult)
            worst = min(points_by_mult)
            best_idx = points_by_mult.index(best)
            worst_idx = points_by_mult.index(worst)
            sensitivity_slices.append(
                SensitivitySlice(
                    axis=axis_label,
                    baseline=baseline,
                    worst=worst,
                    best=best,
                    worst_multiplier=multiplier_labels[worst_idx],
                    best_multiplier=multiplier_labels[best_idx],
                )
            )

    # --- Build inputs + visuals -------------------------------------------
    inputs = compute_aggregates(
        currency=currency,
        monthly=monthly,
        category_breakdown=category_breakdown,
        alerts=triggered,
        sensitivity=sensitivity_slices,
        runway_months=runway_months,
    )
    visuals_raw = build_dashboard_insights(inputs)

    # --- Response (visual payloads) ----------------------------------------
    visuals = [
        DashboardVisual(
            visual_id=v.visual_id,
            title=v.title,
            what_it_shows=v.what_it_shows,
            what_to_notice=list(v.what_to_notice),
            why_it_matters=v.why_it_matters,
            evidence=v.evidence,
        )
        for v in visuals_raw
    ]

    horizon_months = max(1, months_between(buckets[0].start, buckets[-1].end_exclusive))
    total_costs = quantize(total_direct + total_opex, currency)
    operating_profit_total = quantize(total_revenue - total_direct - total_opex, currency)

    return DashboardInsightsResponse(
        business_id=business.id,
        currency=currency,
        period_start=period_start.isoformat(),
        period_end_exclusive=period_end_exclusive.isoformat(),
        calculation_timestamp=datetime.now(timezone.utc).isoformat(),
        visuals=visuals,
        alerts_count=len(triggered),
        financing_counts={},
        summary={
            "is_empty": False,
            "horizon_months": horizon_months,
            "revenue": format_money(total_revenue, currency),
            "total_costs": format_money(total_costs, currency),
            "operating_profit": format_money(operating_profit_total, currency),
            "operating_margin": safe_div_str(
                operating_profit_total, total_revenue, currency, places=4
            ),
            "closing_cash": format_money(closing_final, currency),
            "runway_months": str(runway_months) if runway_months is not None else None,
            "transaction_count": len(rows_in_window),
        },
    )


__all__ = ["router"]
