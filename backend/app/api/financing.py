"""Financing-options endpoint.

Pulls the synthetic catalog from ``sample_data/financing_catalog.json``,
gathers the deterministic business metrics the matcher needs (avg monthly
revenue, average monthly operating profit, months operating, and the
projected cash trajectory), then runs the pure matcher. The LLM and
Laya never participate.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engine.alerts import (
    AlertConfig,
    MonthlyCashPoint,
)
from app.engine.financing import (
    FinancingContext,
    FinancingProduct,
    compute_funding_need_from_points,
    load_catalog,
    match_financing,
)
from app.models.business import Business
from app.models.transaction import Transaction
from app.schemas.financing import (
    EligibilityCheckRead,
    FinancingCatalog,
    FinancingMatchRead,
    FinancingOptionsResponse,
    FinancingProductCatalogEntry,
    NoFinancingNeededRead,
)
from app.schemas.money import Currency
from app.services.finance.metrics import (
    DIRECT_COST_CATEGORIES,
    OPEX_CATEGORIES,
    Transaction as EngineTx,
    compute_metrics,
)
from app.services.finance.money import ZERO, format_money
from app.services.finance.periods import MonthlyPeriod, months_between

router = APIRouter(prefix="/businesses", tags=["financing"])

CATALOG_PATH = (
    Path(__file__).resolve().parents[3] / "sample_data" / "financing_catalog.json"
)


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


def _load_catalog_or_500() -> tuple[list[FinancingProduct], FinancingCatalog]:
    try:
        products, meta = load_catalog(CATALOG_PATH)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"catalog_missing: {exc}") from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=500, detail=f"catalog_invalid: {exc}") from exc
    catalog = FinancingCatalog(
        products=[
            FinancingProductCatalogEntry(
                id=p.id,
                name=p.name,
                type=p.type,
                min_amount=str(p.min_amount),
                max_amount=str(p.max_amount),
                min_months_operating=p.min_months_operating,
                min_avg_monthly_revenue=str(p.min_avg_monthly_revenue),
                max_term_months=p.max_term_months,
                indicative_annual_rate=str(p.indicative_annual_rate),
                suitable_use_cases=list(p.suitable_use_cases),
                synthetic=p.synthetic,
            )
            for p in products
        ],
        synthetic=bool(meta.get("_synthetic", True)),
    )
    return products, catalog


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/{business_id}/financing-options", response_model=FinancingOptionsResponse)
def get_financing_options(
    business_id: str,
    db: Session = Depends(get_db),
) -> FinancingOptionsResponse:
    """Match a business against the SYNTHETIC financing catalog."""
    business = db.get(Business, business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="business_not_found")

    currency = Currency(business.currency)
    products, catalog = _load_catalog_or_500()

    rows = (
        db.query(Transaction)
        .filter(Transaction.business_id == business_id)
        .order_by(Transaction.tx_date.asc())
        .all()
    )

    # --- Deterministic aggregates from persisted transactions -------------
    if not rows:
        return FinancingOptionsResponse(
            business_id=business.id,
            currency=currency,
            funding_need="0",
            minimum_projected_cash="0",
            avg_monthly_revenue="0",
            monthly_operating_profit="0",
            months_operating=0,
            catalog=catalog,
            matches=[],
            no_financing_needed=NoFinancingNeededRead(
                reason=(
                    "No transactions yet. The matcher needs a cash trajectory "
                    "and revenue history before it can recommend products."
                ),
                minimum_projected_cash="0",
                funding_need="0",
            ),
        )

    buckets = _bucket_by_month(rows)
    points: list[MonthlyCashPoint] = []
    total_revenue = ZERO
    total_cogs = ZERO
    total_opex = ZERO
    opening_running = ZERO

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
                opening_cash=opening_running,
                net_cash_movement=net,
                closing_cash=closing,
            )
        )
        for t in txs_in_bucket:
            amt = t.amount
            if t.direction == "inflow":
                total_revenue += amt
            else:
                cat = (t.category or "").lower()
                if cat in DIRECT_COST_CATEGORIES:
                    total_cogs += amt
                elif cat in OPEX_CATEGORIES:
                    total_opex += amt
        opening_running = closing

    months_observed = max(1, months_between(buckets[0].start, buckets[-1].end_exclusive))
    avg_monthly_revenue_dec = total_revenue / Decimal(months_observed)
    monthly_op_profit_dec = (total_revenue - total_cogs - total_opex) / Decimal(months_observed)

    months_operating = months_observed
    funding_need = compute_funding_need_from_points(
        points=points,
        min_buffer=AlertConfig().low_buffer_months * monthly_op_profit_dec
        if monthly_op_profit_dec > ZERO
        else ZERO,
    )

    context = FinancingContext(
        currency=business.currency,
        funding_need=funding_need,
        months_operating=months_operating,
        avg_monthly_revenue=avg_monthly_revenue_dec,
        monthly_operating_profit=monthly_op_profit_dec,
        monthly_cash=tuple(points),
    )

    outcome = match_financing(context=context, products=products)

    if outcome.no_financing_needed is not None:
        return FinancingOptionsResponse(
            business_id=business.id,
            currency=currency,
            funding_need=outcome.funding_need,
            minimum_projected_cash=outcome.minimum_projected_cash,
            avg_monthly_revenue=format_money(avg_monthly_revenue_dec, business.currency),
            monthly_operating_profit=format_money(monthly_op_profit_dec, business.currency),
            months_operating=months_operating,
            catalog=catalog,
            matches=[],
            no_financing_needed=NoFinancingNeededRead(
                reason=outcome.no_financing_needed.reason,
                minimum_projected_cash=outcome.no_financing_needed.minimum_projected_cash,
                funding_need=outcome.no_financing_needed.funding_need,
            ),
        )

    return FinancingOptionsResponse(
        business_id=business.id,
        currency=currency,
        funding_need=outcome.funding_need,
        minimum_projected_cash=outcome.minimum_projected_cash,
        avg_monthly_revenue=format_money(avg_monthly_revenue_dec, business.currency),
        monthly_operating_profit=format_money(monthly_op_profit_dec, business.currency),
        months_operating=months_operating,
        catalog=catalog,
        matches=[
            FinancingMatchRead(
                product_id=m.product_id,
                product_name=m.product_name,
                product_type=m.product_type,
                label=m.label,
                fit_reasons=list(m.fit_reasons),
                unmet_criteria=list(m.unmet_criteria),
                checks=[
                    EligibilityCheckRead(
                        name=c.name,
                        passed=c.passed,
                        requirement=c.requirement,
                        actual=c.actual,
                    )
                    for c in m.checks
                ],
                indicative_annual_rate=m.indicative_annual_rate,
                requested_amount=m.requested_amount,
                term_months=m.term_months,
                monthly_repayment=m.monthly_repayment,
                dscr=m.dscr,
                synthetic=m.synthetic,
            )
            for m in outcome.matches
        ],
        no_financing_needed=None,
    )


__all__ = ["router"]