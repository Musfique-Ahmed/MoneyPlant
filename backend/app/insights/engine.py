"""Dashboard-insights engine.

Pure functions only. Consumes already-computed engine numbers (per-month
metrics, alerts, per-category totals) and returns a list of
:class:`Visual` payloads that the frontend renders with the matching chart.

Every quoted figure is taken verbatim from the input so the API layer
can never accidentally invent a number — and the test suite asserts that.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from app.engine.alerts import Alert
from app.services.finance.money import (
    ZERO,
    format_money,
    quantize,
    safe_div_str,
)


# ---------------------------------------------------------------------------
# Inputs / outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MonthlyAggregate:
    """One month of every metric the dashboard needs.

    All Decimals. All pre-formatted strings are produced in the
    API layer via :func:`format_money`. The insight text uses the
    formatted strings so the frontend can do literal text comparison.
    """

    month_index: int
    month_label: str  # e.g. "2026-03" (month bucket label from the engine)
    revenue: Decimal
    direct_costs: Decimal
    operating_expenses: Decimal
    operating_profit: Decimal
    gross_profit: Decimal
    cash_inflows: Decimal
    cash_outflows: Decimal
    net_cash_movement: Decimal
    opening_cash: Decimal
    closing_cash: Decimal
    # Cost category breakdown (Decimal total per category; rest sum to direct_costs+opex).
    cost_by_category: dict[str, Decimal]

    def total_costs(self, currency: str = "USD") -> Decimal:
        return _safe_add(self.direct_costs, self.operating_expenses, currency)

    # Backwards-compatible alias used by older generator bodies.
    @property
    def total_costs_real(self) -> Decimal:
        return _safe_add(self.direct_costs, self.operating_expenses, "USD")


@dataclass(frozen=True)
class CategoryTotal:
    category: str
    amount: Decimal


@dataclass(frozen=True)
class SensitivitySlice:
    """One axis of a sensitivity sweep. """
    axis: str               # human-readable axis name
    baseline: Decimal
    worst: Decimal          # most-negative operating_profit among the multipliers
    best: Decimal           # most-positive operating_profit among the multipliers
    worst_multiplier: str
    best_multiplier: str


@dataclass(frozen=True)
class DashboardInputs:
    currency: str
    monthly: tuple[MonthlyAggregate, ...]
    category_breakdown: tuple[CategoryTotal, ...]
    alerts: tuple[Alert, ...]
    sensitivity: tuple[SensitivitySlice, ...] = ()
    runway_months: Decimal | None = None
    # Optional: explicit opening cash considered (defaults to first month).
    opening_cash_override: Decimal | None = None


@dataclass(frozen=True)
class Visual:
    visual_id: str
    title: str
    what_it_shows: str
    what_to_notice: tuple[str, ...]
    why_it_matters: str
    evidence: dict[str, object]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_add(a: Decimal, b: Decimal, currency: str) -> Decimal:
    return quantize(a + b, currency)


def _d(value: object, currency: str) -> str:
    """Format a value as money, treating ``None`` / empty string as em-dash."""
    if value is None or value == "":
        return "—"
    if isinstance(value, str):
        return format_money(value, currency) if value != "" else "—"
    if isinstance(value, Decimal):
        return format_money(value, currency)
    return str(value)


def _dm(value: Decimal, currency: str) -> str:
    """Always-format-as-money: the canonical monetary evidence string."""
    return format_money(value, currency)


def _signed_pct_change(current: Decimal, prior: Decimal, currency: str) -> str | None:
    """Percent change vs prior period. Returns ``None`` when prior is zero."""
    if prior == ZERO:
        return None
    change = (current - prior) / prior
    pct = change * Decimal(100)
    return safe_div_str(Decimal(pct), Decimal(1), currency, places=1)


def _trend_label(series: Iterable[Decimal]) -> str:
    """Plain-English trend label: rising, falling, flat, mixed."""
    values = list(series)
    if len(values) < 2:
        return "flat"
    rising = sum(1 for a, b in zip(values, values[1:]) if b > a)
    falling = sum(1 for a, b in zip(values, values[1:]) if b < a)
    if rising == 0 and falling == 0:
        return "flat"
    if rising > 0 and falling == 0:
        return "rising"
    if falling > 0 and rising == 0:
        return "falling"
    return "mixed"


def _peak_label(values: Iterable[Decimal], labels: list[str]) -> str:
    """Return the label of the month with the maximum value."""
    pairs = list(zip(values, labels))
    if not pairs:
        return ""
    v, lbl = max(pairs, key=lambda x: x[0])
    return lbl


def _trough_label(values: Iterable[Decimal], labels: list[str]) -> str:
    pairs = list(zip(values, labels))
    if not pairs:
        return ""
    v, lbl = min(pairs, key=lambda x: x[0])
    return lbl


def _avg_monthly_outflow(monthly: list[MonthlyAggregate], currency: str) -> Decimal:
    outflows = [-(m.net_cash_movement) for m in monthly if m.net_cash_movement < ZERO]
    if not outflows:
        return ZERO
    return quantize(sum(outflows, ZERO) / Decimal(len(outflows)), currency)


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def compute_aggregates(
    *,
    currency: str,
    monthly: list[MonthlyAggregate],
    category_breakdown: list[CategoryTotal],
    alerts: list[Alert],
    sensitivity: list[SensitivitySlice] | None = None,
    runway_months: Decimal | None = None,
    opening_cash_override: Decimal | None = None,
) -> DashboardInputs:
    return DashboardInputs(
        currency=currency,
        monthly=tuple(monthly),
        category_breakdown=tuple(category_breakdown),
        alerts=tuple(alerts),
        sensitivity=tuple(sensitivity or []),
        runway_months=runway_months,
        opening_cash_override=opening_cash_override,
    )


# ---------------------------------------------------------------------------
# Edge-case sentence builders
# ---------------------------------------------------------------------------


def _edge_case_visual(*, visual_id: str, title: str, reason: str) -> Visual:
    return Visual(
        visual_id=visual_id,
        title=title,
        what_it_shows=reason,
        what_to_notice=("Import or run a scenario to populate the dashboard.",),
        why_it_matters=(
            "Without at least one month of activity, none of the insight rules "
            "have data to operate on — and we never show fabricated numbers."
        ),
        evidence={"reason": reason, "kind": "edge_case"},
    )


# ---------------------------------------------------------------------------
# 1. KPI strip
# ---------------------------------------------------------------------------


def kpi_visual(inputs: DashboardInputs) -> Visual:
    cur = inputs.currency
    monthly = inputs.monthly
    if len(monthly) == 0:
        return _edge_case_visual(
            visual_id="kpi",
            title="Key metrics",
            reason="No months of activity yet.",
        )

    last = monthly[-1]
    prior = monthly[-2] if len(monthly) >= 2 else None

    rev_change_pct = _signed_pct_change(last.revenue, prior.revenue, cur) if prior else None
    cost_change_pct = (
        _signed_pct_change(last.total_costs_real, prior.total_costs_real, cur) if prior else None
    )
    profit_change_pct = (
        _signed_pct_change(last.operating_profit, prior.operating_profit, cur) if prior else None
    )
    cash_change_pct = (
        _signed_pct_change(last.closing_cash, prior.closing_cash, cur) if prior else None
    )

    notice: list[str] = []
    if rev_change_pct is not None and cost_change_pct is not None:
        if Decimal(rev_change_pct) < Decimal(cost_change_pct):
            notice.append(
                "Costs grew faster than revenue between "
                f"{prior.month_label if prior else 'the previous month'} and {last.month_label} "
                f"({rev_change_pct}% revenue vs {cost_change_pct}% costs)."
            )
        elif Decimal(rev_change_pct) > Decimal(cost_change_pct):
            notice.append(
                f"Revenue grew faster than costs ({rev_change_pct}% vs {cost_change_pct}%) "
                f"between {prior.month_label if prior else 'last'} and {last.month_label}."
            )
    if last.operating_profit < ZERO:
        notice.append(
            f"Operating profit is negative ({_d(last.operating_profit, cur)}) in {last.month_label}."
        )
    if inputs.runway_months is not None and Decimal(inputs.runway_months) < Decimal(1):
        notice.append(
            f"Runway is below 1 month ({inputs.runway_months} months)."
        )

    if not notice:
        notice.append(
            f"Latest month ({last.month_label}): "
            f"revenue {_d(last.revenue, cur)}, "
            f"operating profit {_d(last.operating_profit, cur)}, "
            f"closing cash {_d(last.closing_cash, cur)}."
        )

    return Visual(
        visual_id="kpi",
        title="Key metrics",
        what_it_shows=(
            "Revenue, total costs, operating profit, closing cash, and cash runway "
            "for the latest month, with the change versus the previous month."
        ),
        what_to_notice=tuple(notice),
        why_it_matters=(
            "These five numbers are the ones an SME owner usually wants at a glance. "
            "Closing cash tells you what is in the bank today; runway tells you how many "
            "months that balance would cover at the current average outflow."
        ),
        evidence={
            "currency": cur,
            "month_label": last.month_label,
            "previous_label": prior.month_label if prior else None,
            "revenue": _dm(last.revenue, cur),
            "total_costs": _dm(last.total_costs_real, cur),
            "operating_profit": _dm(last.operating_profit, cur),
            "closing_cash": _dm(last.closing_cash, cur),
            "runway_months": str(inputs.runway_months) if inputs.runway_months is not None else None,
            "revenue_change_pct": rev_change_pct,
            "cost_change_pct": cost_change_pct,
            "profit_change_pct": profit_change_pct,
            "cash_change_pct": cash_change_pct,
        },
    )


# ---------------------------------------------------------------------------
# 2. Revenue vs costs vs profit (combo chart)
# ---------------------------------------------------------------------------


def revenue_costs_profit_visual(inputs: DashboardInputs) -> Visual:
    cur = inputs.currency
    monthly = inputs.monthly
    if not monthly:
        return _edge_case_visual(
            visual_id="revenue_costs_profit",
            title="Revenue, costs, and operating profit",
            reason="No months of activity yet.",
        )

    revs = [m.revenue for m in monthly]
    costs = [m.total_costs_real for m in monthly]
    profits = [m.operating_profit for m in monthly]

    peak_month = _peak_label(revs, [m.month_label for m in monthly])
    trough_month = _trough_label(revs, [m.month_label for m in monthly])

    notice: list[str] = []
    if peak_month and trough_month and peak_month != trough_month:
        notice.append(
            f"Revenue peaked in {peak_month} ({_d(max(revs), cur)}) and bottomed in "
            f"{trough_month} ({_d(min(revs), cur)})."
        )
    profit_negative_months = [m for m, p in zip(monthly, profits) if p < ZERO]
    if profit_negative_months:
        notice.append(
            f"Operating profit went negative in "
            f"{', '.join(m.month_label for m in profit_negative_months)}."
        )
    trend = _trend_label(profits)
    notice.append(f"Operating profit trend: {trend}.")

    return Visual(
        visual_id="revenue_costs_profit",
        title="Revenue, costs, and operating profit",
        what_it_shows=(
            "Monthly revenue (bar), total costs (bar), and operating profit (line). "
            "When the profit line sits between the two bars, costs are below revenue."
        ),
        what_to_notice=tuple(notice),
        why_it_matters=(
            "If the line stays below the cost bar for two or more months, pricing or "
            "cost structure is the first thing to revisit — not sales volume."
        ),
        evidence={
            "currency": cur,
            "months": [
                {
                    "month_label": m.month_label,
                    "revenue": _dm(m.revenue, cur),
                    "total_costs": _dm(m.total_costs_real, cur),
                    "operating_profit": _dm(m.operating_profit, cur),
                }
                for m in monthly
            ],
            "peak_revenue_month": peak_month,
            "trough_revenue_month": trough_month,
            "profit_trend": trend,
        },
    )


# ---------------------------------------------------------------------------
# 3. Cash balance over time
# ---------------------------------------------------------------------------


def cash_balance_visual(inputs: DashboardInputs) -> Visual:
    cur = inputs.currency
    monthly = inputs.monthly
    if not monthly:
        return _edge_case_visual(
            visual_id="cash_balance",
            title="Cash balance over time",
            reason="No months of activity yet.",
        )

    closing_values = [m.closing_cash for m in monthly]
    labels = [m.month_label for m in monthly]

    min_month = _trough_label(closing_values, labels)
    max_month = _peak_label(closing_values, labels)

    avg_outflow = _avg_monthly_outflow(monthly, cur)
    min_buffer = avg_outflow if avg_outflow > ZERO else ZERO

    negative_months = [m for m in monthly if m.closing_cash < ZERO]

    alert_codes = sorted({a.code for a in inputs.alerts if a.code in {
        "NEGATIVE_CASH", "LOW_BUFFER", "SHORT_RUNWAY", "SHARP_DROP"
    }})
    alert_months_by_code: dict[str, list[str]] = {}
    for a in inputs.alerts:
        if a.month is None:
            continue
        if a.month - 1 >= len(monthly):
            continue
        m_label = monthly[a.month - 1].month_label
        alert_months_by_code.setdefault(a.code, []).append(m_label)

    notice: list[str] = []
    if min_month and max_month:
        notice.append(
            f"Cash peaked in {max_month} ({_d(max(closing_values), cur)}) and bottomed in "
            f"{min_month} ({_d(min(closing_values), cur)})."
        )
    if negative_months:
        notice.append(
            "Closing cash was negative in "
            + ", ".join(m.month_label for m in negative_months)
            + "."
        )
    if min_buffer > ZERO and any(m.closing_cash < min_buffer for m in monthly):
        below = [m.month_label for m in monthly if m.closing_cash < min_buffer]
        notice.append(
            f"Closing cash fell below the 1-month buffer ({_d(min_buffer, cur)}) in "
            + ", ".join(below) + "."
        )
    if not notice:
        notice.append(
            "Closing cash stayed within a 1-month buffer of average outflows."
        )

    return Visual(
        visual_id="cash_balance",
        title="Cash balance over time",
        what_it_shows=(
            f"Closing cash per month with a zero line and a 1-month operating buffer. "
            f"Months with relevant alerts ({', '.join(alert_codes) or 'none'}) are linked."
        ),
        what_to_notice=tuple(notice),
        why_it_matters=(
            "Negative cash is the only signal that, on its own, can shut a business. "
            "A buffer below one month of average costs means the business is living "
            "hand-to-mouth."
        ),
        evidence={
            "currency": cur,
            "min_buffer": format_money(min_buffer, cur),
            "months": [
                {
                    "month_label": m.month_label,
                    "opening_cash": format_money(m.opening_cash, cur),
                    "net_cash_movement": format_money(m.net_cash_movement, cur),
                    "closing_cash": format_money(m.closing_cash, cur),
                    "is_negative": m.closing_cash < ZERO,
                }
                for m in monthly
            ],
            "alerts_by_month_code": alert_months_by_code,
        },
    )


# ---------------------------------------------------------------------------
# 4. Profit vs cash gap
# ---------------------------------------------------------------------------


def profit_vs_cash_gap_visual(inputs: DashboardInputs) -> Visual:
    cur = inputs.currency
    monthly = inputs.monthly
    if not monthly:
        return _edge_case_visual(
            visual_id="profit_cash_gap",
            title="Profit vs cash gap",
            reason="No months of activity yet.",
        )

    monthly_gap = [
        m.operating_profit - m.net_cash_movement for m in monthly
    ]
    pbcp_months = [
        m.month_label
        for m, gap in zip(monthly, monthly_gap)
        if m.operating_profit > ZERO and m.net_cash_movement < ZERO
    ]

    credit_signal = [
        m.month_label for m in monthly
        if Decimal("0") < m.operating_profit and m.net_cash_movement < Decimal("0")
        and m.cash_inflows < m.revenue
    ]
    inventory_signal = [
        m.month_label for m in monthly
        if m.cash_outflows > Decimal("0") and m.direct_costs > Decimal("0")
    ]

    notice: list[str] = []
    if pbcp_months:
        joined = ", ".join(pbcp_months)
        reasons: list[str] = []
        if credit_signal:
            reasons.append(
                "cash receipts lagged revenue in "
                + ", ".join(sorted(set(credit_signal)))
            )
        if inventory_signal:
            reasons.append(
                "supplier outflows landed earlier than consumption in "
                + ", ".join(sorted(set(inventory_signal)))
            )
        reasons_str = "; ".join(reasons) if reasons else "credit sales or inventory build-up"
        notice.append(
            f"Profitable but cash-poor: operating profit positive but cash fell in {joined} — "
            f"likely {reasons_str}."
        )
    else:
        notice.append(
            "No month had positive profit alongside negative cash. "
            "If this is unexpected, see the Alerts panel for context."
        )

    return Visual(
        visual_id="profit_cash_gap",
        title="Profit vs cash gap",
        what_it_shows=(
            "Operating profit minus net cash movement per month. Positive bars mean "
            "the business booked profit but did not collect it; negative bars mean it "
            "burned cash despite a loss or a flat profit."
        ),
        what_to_notice=tuple(notice),
        why_it_matters=(
            "Profit that does not turn into cash is the most common cause of "
            "small-business insolvency. A persistent positive gap usually means "
            "credit sales or inventory build-up."
        ),
        evidence={
            "currency": cur,
            "months": [
                {
                    "month_label": m.month_label,
                    "operating_profit": _dm(m.operating_profit, cur),
                    "net_cash_movement": _dm(m.net_cash_movement, cur),
                    "gap": _dm(m.operating_profit - m.net_cash_movement, cur),
                }
                for m in monthly
            ],
            "profitable_but_cash_poor_months": pbcp_months,
            "credit_lag_signals": credit_signal,
            "inventory_signals": inventory_signal,
        },
    )


# ---------------------------------------------------------------------------
# 5. Cost breakdown by category
# ---------------------------------------------------------------------------


def cost_breakdown_visual(inputs: DashboardInputs) -> Visual:
    cur = inputs.currency
    cats = inputs.category_breakdown
    if not cats:
        return _edge_case_visual(
            visual_id="cost_breakdown",
            title="Cost breakdown by category",
            reason="No cost categories recorded yet.",
        )

    total = sum((c.amount for c in cats), ZERO)
    if total == ZERO:
        return _edge_case_visual(
            visual_id="cost_breakdown",
            title="Cost breakdown by category",
            reason="Total costs were zero in this period.",
        )

    sorted_cats = sorted(cats, key=lambda c: c.amount, reverse=True)
    biggest = sorted_cats[0]
    biggest_share = quantize(biggest.amount / total, cur)
    notice = [
        f"'{biggest.category}' is the biggest cost at {_d(biggest.amount, cur)} "
        f"({safe_div_str(biggest_share, Decimal(1), cur, places=1)} of total)."
    ]
    if len(sorted_cats) >= 3:
        top3_total = sum(c.amount for c in sorted_cats[:3])
        top3_share = quantize(top3_total / total, cur)
        notice.append(
            f"The top three cost categories total {_d(top3_total, cur)} "
            f"({safe_div_str(top3_share, Decimal(1), cur, places=1)} of total costs)."
        )

    return Visual(
        visual_id="cost_breakdown",
        title="Cost breakdown by category",
        what_it_shows="Every recorded cost category, ordered from largest to smallest.",
        what_to_notice=tuple(notice),
        why_it_matters=(
            "Concentration in one or two categories is the lever with the highest ROI — "
            "those are the categories where renegotiating a supplier or trimming a few "
            "items has the largest effect on operating profit."
        ),
        evidence={
            "currency": cur,
            "total": _dm(total, cur),
            "categories": [
                {
                    "category": c.category,
                    "amount": _dm(c.amount, cur),
                    "share": str(quantize(c.amount / total, cur)),
                }
                for c in sorted_cats
            ],
        },
    )


# ---------------------------------------------------------------------------
# 6. Scenario comparison (driven by caller-provided rows)
# ---------------------------------------------------------------------------


def scenario_compare_visual(
    *,
    visual_id: str,
    inputs: DashboardInputs,
    baseline_label: str,
    alt_label: str,
    baseline_revenue: Decimal,
    baseline_profit: Decimal,
    baseline_closing_cash: Decimal,
    baseline_runway: Decimal | None,
    alt_revenue: Decimal,
    alt_profit: Decimal,
    alt_closing_cash: Decimal,
    alt_runway: Decimal | None,
) -> Visual:
    cur = inputs.currency

    def _signed_pct(a: Decimal, b: Decimal) -> str | None:
        if b == ZERO:
            return None
        return safe_div_str((a - b) / b, Decimal(1), cur, places=2)

    rev_pct = _signed_pct(alt_revenue, baseline_revenue)
    profit_pct = _signed_pct(alt_profit, baseline_profit)
    cash_pct = _signed_pct(alt_closing_cash, baseline_closing_cash)
    runway_diff = (
        (alt_runway or Decimal(0)) - (baseline_runway or Decimal(0))
        if (alt_runway is not None and baseline_runway is not None)
        else None
    )

    notice: list[str] = []
    if profit_pct is not None:
        direction = "up" if Decimal(profit_pct) > 0 else "down"
        notice.append(
            f"Operating profit moves {direction} {profit_pct}% "
            f"({_d(baseline_profit, cur)} → {_d(alt_profit, cur)})."
        )
    if rev_pct is not None and Decimal(rev_pct) > 0:
        notice.append(f"Revenue increases {rev_pct}%.")
    if cash_pct is not None and Decimal(cash_pct) < 0:
        notice.append(
            f"Closing cash decreases {cash_pct[1:]}% ({_d(alt_closing_cash, cur)} vs "
            f"{_d(baseline_closing_cash, cur)})."
        )
    if runway_diff is not None:
        notice.append(
            f"Cash runway changes by {runway_diff:+.2f} months."
        )

    return Visual(
        visual_id=visual_id,
        title=f"Scenario: {baseline_label} vs {alt_label}",
        what_it_shows=(
            f"Side-by-side of revenue, operating profit, closing cash, and runway for "
            f"'{baseline_label}' (baseline) and '{alt_label}' (alternative)."
        ),
        what_to_notice=tuple(notice),
        why_it_matters=(
            "Always check the cash side, not just the profit side. A scenario that "
            "improves profit but hurts cash within the planning horizon is usually "
            "worse than doing nothing."
        ),
        evidence={
            "currency": cur,
            "baseline_label": baseline_label,
            "alt_label": alt_label,
            "baseline": {
                "revenue": str(baseline_revenue),
                "operating_profit": str(baseline_profit),
                "closing_cash": str(baseline_closing_cash),
                "runway_months": str(baseline_runway) if baseline_runway is not None else None,
            },
            "alt": {
                "revenue": str(alt_revenue),
                "operating_profit": str(alt_profit),
                "closing_cash": str(alt_closing_cash),
                "runway_months": str(alt_runway) if alt_runway is not None else None,
            },
            "deltas": {
                "revenue_pct": rev_pct,
                "profit_pct": profit_pct,
                "cash_pct": cash_pct,
                "runway_diff_months": str(runway_diff) if runway_diff is not None else None,
            },
        },
    )


# ---------------------------------------------------------------------------
# 7. Sensitivity
# ---------------------------------------------------------------------------


def sensitivity_visual(
    *,
    visual_id: str,
    inputs: DashboardInputs,
    title: str = "Sensitivity: which input moves profit the most?",
) -> Visual:
    cur = inputs.currency
    slices = inputs.sensitivity
    if not slices:
        return _edge_case_visual(
            visual_id=visual_id,
            title=title,
            reason="No sensitivity sweep available. Run a saved scenario with sensitivity enabled.",
        )

    # Range = best - worst in absolute terms (a sweep that goes both ways).
    ranged = sorted(
        ((s, abs(s.best - s.worst)) for s in slices),
        key=lambda x: x[1],
        reverse=True,
    )
    top = ranged[0][0]
    bottom = ranged[-1][0]

    notice = [
        f"The '{top.axis}' input swings operating profit the most "
        f"({_d(top.worst, cur)} at {top.worst_multiplier} → {_d(top.best, cur)} at {top.best_multiplier})."
    ]
    if ranged and top.axis != bottom.axis:
        notice.append(
            f"The '{bottom.axis}' input is the least impactful lever in this sweep."
        )

    return Visual(
        visual_id=visual_id,
        title=title,
        what_it_shows=(
            "One-at-a-time deterministic sensitivity: each axis changes one input while "
            "holding others constant, and reports the resulting operating profit. "
            "This is not a forecast — it tells you which lever is worth pulling."
        ),
        what_to_notice=tuple(notice),
        why_it_matters=(
            "If the largest swing comes from a cost line, focus there first; if from a "
            "price or volume line, focus on revenue. Either way, you know where a "
            "10% change actually shows up."
        ),
        evidence={
            "currency": cur,
            "axes": [
                {
                    "axis": s.axis,
                    "baseline": _dm(s.baseline, cur),
                    "worst": _dm(s.worst, cur),
                    "worst_multiplier": s.worst_multiplier,
                    "best": _dm(s.best, cur),
                    "best_multiplier": s.best_multiplier,
                    "range": _dm(abs(s.best - s.worst), cur),
                }
                for s in slices
            ],
        },
    )


# ---------------------------------------------------------------------------
# 8. Alerts and financing summary
# ---------------------------------------------------------------------------


def alerts_summary_visual(*, inputs: DashboardInputs, visual_id: str = "alerts_summary") -> Visual:
    cur = inputs.currency
    alerts = inputs.alerts
    counts = {"Critical": 0, "Warning": 0, "Info": 0}
    for a in alerts:
        if a.severity in counts:
            counts[a.severity] += 1  # type: ignore[index]
    if not alerts:
        return Visual(
            visual_id=visual_id,
            title="Cash-flow alerts",
            what_it_shows="No cash-flow alerts triggered over the selected period.",
            what_to_notice=("All thresholds within bounds.",),
            why_it_matters=(
                "When you see no alerts, the engine has not found anything the metrics say "
                "you should look at. It does not mean the data is correct."
            ),
            evidence={"counts": counts, "total": 0},
        )
    lead_severity = (
        "Critical" if counts["Critical"] > 0
        else "Warning" if counts["Warning"] > 0
        else "Info"
    )
    return Visual(
        visual_id=visual_id,
        title="Cash-flow alerts",
        what_it_shows=(
            f"{len(alerts)} deterministic alert(s) over the selected period: "
            f"{counts['Critical']} Critical, {counts['Warning']} Warning, {counts['Info']} Info. "
            f"Leading severity: {lead_severity}."
        ),
        what_to_notice=tuple(a.message for a in alerts[:3]),
        why_it_matters=(
            "Each alert comes with the exact input it used and a small evidence dict, "
            "so the panel next to it is the audit trail, not just a headline."
        ),
        evidence={
            "currency": cur,
            "counts": counts,
            "total": len(alerts),
            "lead_severity": lead_severity,
            "alerts_evidence": [
                {"code": a.code, "severity": a.severity, "month": a.month,
                 "closing_cash": a.evidence.get("closing_cash") if isinstance(a.evidence, dict) else None}
                for a in alerts
            ],
        },
    )


def financing_summary_visual(
    *,
    inputs: DashboardInputs,
    funding_need: Decimal | None,
    catalog_synthetic: bool,
    match_counts: dict[str, int],
    visual_id: str = "financing_summary",
) -> Visual:
    cur = inputs.currency
    funding_str = (
        _d(funding_need, cur) if funding_need is not None else "—"
    )
    notice: list[str] = []
    if funding_need is None or funding_need == ZERO:
        notice.append("No projected cash shortfall — financing is not required.")
    else:
        notice.append(
            f"Projected funding need is {_d(funding_need, cur)}."
        )
        notice.append(
            "Recommended: {0}; Possible: {1}; Not recommended: {2}.".format(
                match_counts.get("recommended", 0),
                match_counts.get("possible", 0),
                match_counts.get("not_recommended", 0),
            )
        )

    return Visual(
        visual_id=visual_id,
        title="Financing options (illustrative)",
        what_it_shows=(
            f"Funding need: {funding_str}. "
            f"The catalog is {'synthetic' if catalog_synthetic else 'real'} — see disclaimer on the panel. "
            f"All product labels are matched text (recommended / possible / not recommended)."
        ),
        what_to_notice=tuple(notice),
        why_it_matters=(
            "Even when an illustrative catalog fits on paper, only a real lender with your "
            "actual accounts can tell you what they will approve. Use the match to shortlist "
            "the conversation, not the conclusion."
        ),
        evidence={
            "currency": cur,
            "funding_need": str(funding_need) if funding_need is not None else None,
            "catalog_synthetic": catalog_synthetic,
            "match_counts": match_counts,
        },
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def build_dashboard_insights(inputs: DashboardInputs) -> list[Visual]:
    """Run every generator in a stable order."""
    out: list[Visual] = [
        kpi_visual(inputs),
        revenue_costs_profit_visual(inputs),
        cash_balance_visual(inputs),
        profit_vs_cash_gap_visual(inputs),
        cost_breakdown_visual(inputs),
    ]
    if inputs.sensitivity:
        out.append(sensitivity_visual(visual_id="sensitivity", inputs=inputs))
    if inputs.alerts:
        out.append(alerts_summary_visual(inputs=inputs))
    return out


__all__ = [
    "MonthlyAggregate",
    "CategoryTotal",
    "SensitivitySlice",
    "DashboardInputs",
    "Visual",
    "compute_aggregates",
    "build_dashboard_insights",
    "kpi_visual",
    "revenue_costs_profit_visual",
    "cash_balance_visual",
    "profit_vs_cash_gap_visual",
    "cost_breakdown_visual",
    "scenario_compare_visual",
    "sensitivity_visual",
    "alerts_summary_visual",
    "financing_summary_visual",
]
