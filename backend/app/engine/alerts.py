"""Cash-flow alerts.

A pure module: given a monthly closing-cash series plus headline metrics
already produced by the deterministic engine, return a list of
:class:`Alert` records (no side effects, no I/O). Every threshold lives in
:class:`AlertConfig` so callers can tune without editing code.

Usage (by the API layer)::

    alerts = evaluate_alerts(
        points=monthly_points,        # built by the caller from ``compute_metrics`` per month
        runway_months=Decimal("2.5"),  # from ``ScenarioResult.cash_runway_months``
        operating_profit=Decimal("100"),  # from ``ScenarioResult.operating_profit``
        config=AlertConfig(),
    )
    # alerts is ``list[Alert]``; may be empty when nothing of note is happening.

The module never raises on empty input; it returns ``[]`` so the API
handler can always render an "All clear" state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.services.finance.money import ZERO, format_money, quantize, safe_div_str


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MonthlyCashPoint:
    """One period of a cash trajectory.

    ``month_index`` is 1-based and represents "month 1, 2, 3, ..." from
    the start of the series. ``closing_cash`` is the cumulative cash at
    end-of-month. ``net_cash_movement`` is the change during the month
    (cash_inflows - cash_outflows), and may be negative.
    """

    month_index: int
    opening_cash: Decimal
    net_cash_movement: Decimal
    closing_cash: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "month_index": self.month_index,
            "opening_cash": str(self.opening_cash),
            "net_cash_movement": str(self.net_cash_movement),
            "closing_cash": str(self.closing_cash),
        }


@dataclass(frozen=True)
class AlertConfig:
    """Thresholds for the alert rules. Defaults are sensible for SMB scale; override per business."""

    # Low-buffer: monthly cash falling below this many months of average operating costs.
    low_buffer_months: Decimal = Decimal("1")
    # Runway thresholds. Below 3 months = warning; below 1 month = critical.
    short_runway_warning_months: Decimal = Decimal("3")
    short_runway_critical_months: Decimal = Decimal("1")
    # Sharp-drop: a single month-over-month closing-cash fall greater than this fraction.
    sharp_drop_pct: Decimal = Decimal("0.25")

    def to_dict(self) -> dict[str, str]:
        return {
            "low_buffer_months": str(self.low_buffer_months),
            "short_runway_warning_months": str(self.short_runway_warning_months),
            "short_runway_critical_months": str(self.short_runway_critical_months),
            "sharp_drop_pct": str(self.sharp_drop_pct),
        }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


# Severity labels are part of the public contract — used by the API and the UI.
SEVERITY_CRITICAL = "Critical"
SEVERITY_WARNING = "Warning"
SEVERITY_INFO = "Info"

ALL_SEVERITIES: tuple[str, ...] = (SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_INFO)


@dataclass(frozen=True)
class Alert:
    """A single, deterministic observation about a business's cash trajectory."""

    code: str
    severity: str
    month: int | None
    message: str
    # Arbitrary, JSON-serialisable structure holding the numbers used to decide
    # the alert. The UI renders these so the user can see what we computed.
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "month": self.month,
            "message": self.message,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------------
# Core: per-month helpers
# ---------------------------------------------------------------------------


def _severity_rank(s: str) -> int:
    """Higher rank = more severe. Used for stable ordering when sorting alerts."""
    return {SEVERITY_INFO: 0, SEVERITY_WARNING: 1, SEVERITY_CRITICAL: 2}.get(s, -1)


def _avg_monthly_cost_for(points: list[MonthlyCashPoint], currency: str) -> Decimal:
    """Average monthly operating cost as a properly-quantized Decimal in ``currency``."""
    outflows = [-p.net_cash_movement for p in points if p.net_cash_movement < ZERO]
    if not outflows:
        return ZERO
    total = sum(outflows, ZERO)
    n = Decimal(len(outflows))
    return quantize(total / n, currency)


def _build_monthly_points_from_totals(
    *,
    currency: str,
    opening_cash: Decimal,
    monthly_outflow: Decimal,
    monthly_inflow: Decimal,
    horizon_months: int,
) -> list[MonthlyCashPoint]:
    """Helper used by the API when only "first-period" totals are known.

    The alerts module does not invent schedules beyond what the caller
    supplies; this helper exists to keep the math deterministic when the
    caller intentionally feeds a flat projection. It is *not* used to
    synthesise cash data for transactions — the API layer should bucket
    real transactions per month instead.
    """
    out: list[MonthlyCashPoint] = []
    running = opening_cash
    net = monthly_inflow - monthly_outflow
    for m in range(1, horizon_months + 1):
        opening = running
        closing = quantize(opening + net, currency)
        out.append(
            MonthlyCashPoint(
                month_index=m,
                opening_cash=quantize(opening, currency),
                net_cash_movement=quantize(net, currency),
                closing_cash=closing,
            )
        )
        running = closing
    return out


# ---------------------------------------------------------------------------
# Core: rule evaluation
# ---------------------------------------------------------------------------


def evaluate_alerts(
    *,
    points: list[MonthlyCashPoint],
    runway_months: Decimal | None,
    operating_profit: Decimal,
    currency: str,
    config: AlertConfig | None = None,
) -> list[Alert]:
    """Evaluate the full set of cash-flow rules and return the triggered alerts.

    Pure function. Never raises on empty input — returns an empty list.
    Output is sorted by (severity desc, month asc, code asc) so the
    dashboard always renders in a stable order.
    """
    cfg = config or AlertConfig()
    alerts: list[Alert] = []

    if not points:
        return alerts

    # --- 1. NEGATIVE_CASH: closing cash < 0 at any month ---------------------
    for p in points:
        if p.closing_cash < ZERO:
            alerts.append(
                Alert(
                    code="NEGATIVE_CASH",
                    severity=SEVERITY_CRITICAL,
                    month=p.month_index,
                    message=(
                        f"Projected closing cash is negative in month {p.month_index} "
                        f"({format_money(p.closing_cash, currency)})."
                    ),
                    evidence={
                        "month_index": p.month_index,
                        "opening_cash": format_money(p.opening_cash, currency),
                        "net_cash_movement": format_money(p.net_cash_movement, currency),
                        "closing_cash": format_money(p.closing_cash, currency),
                        "currency": currency,
                    },
                )
            )

    # --- 2. LOW_BUFFER: closing cash < N months of average opex --------------
    avg_cost = _avg_monthly_cost_for(points, currency)
    if avg_cost > ZERO:
        buffer_threshold = quantize(cfg.low_buffer_months * avg_cost, currency)
        for p in points:
            if ZERO <= p.closing_cash < buffer_threshold:
                alerts.append(
                    Alert(
                        code="LOW_BUFFER",
                        severity=SEVERITY_WARNING,
                        month=p.month_index,
                        message=(
                            f"Closing cash in month {p.month_index} is below the "
                            f"{cfg.low_buffer_months}-month operating buffer "
                            f"({format_money(buffer_threshold, currency)})."
                        ),
                        evidence={
                            "month_index": p.month_index,
                            "closing_cash": format_money(p.closing_cash, currency),
                            "buffer_threshold": format_money(buffer_threshold, currency),
                            "avg_monthly_cost": format_money(avg_cost, currency),
                            "low_buffer_months": str(cfg.low_buffer_months),
                            "currency": currency,
                        },
                    )
                )

    # --- 3. SHORT_RUNWAY: cash runway < thresholds ---------------------------
    if runway_months is not None:
        if runway_months < cfg.short_runway_critical_months:
            alerts.append(
                Alert(
                    code="SHORT_RUNWAY",
                    severity=SEVERITY_CRITICAL,
                    month=None,
                    message=(
                        f"Cash runway is {runway_months} months — below the critical "
                        f"threshold of {cfg.short_runway_critical_months}."
                    ),
                    evidence={
                        "runway_months": str(runway_months),
                        "critical_threshold_months": str(cfg.short_runway_critical_months),
                        "currency": currency,
                    },
                )
            )
        elif runway_months < cfg.short_runway_warning_months:
            alerts.append(
                Alert(
                    code="SHORT_RUNWAY",
                    severity=SEVERITY_WARNING,
                    month=None,
                    message=(
                        f"Cash runway is {runway_months} months — below the warning "
                        f"threshold of {cfg.short_runway_warning_months}."
                    ),
                    evidence={
                        "runway_months": str(runway_months),
                        "warning_threshold_months": str(cfg.short_runway_warning_months),
                        "currency": currency,
                    },
                )
            )

    # --- 4. PROFITABLE_BUT_CASH_POOR: positive profit, but closing cash fell ----
    # Reuse the same shape as ``profit_vs_cash.reconcile_profit_and_cash``:
    # profit positive AND cash trajectory is heading downward at the end.
    if operating_profit > ZERO and len(points) >= 2:
        first, last = points[0], points[-1]
        if last.closing_cash < first.opening_cash:
            alerts.append(
                Alert(
                    code="PROFITABLE_BUT_CASH_POOR",
                    severity=SEVERITY_WARNING,
                    month=last.month_index,
                    message=(
                        "Operating profit is positive but closing cash has fallen "
                        f"below the opening cash of the first month "
                        f"({format_money(last.closing_cash, currency)} < "
                        f"{format_money(first.opening_cash, currency)}). "
                        "Likely tied up in receivables, inventory, or one-off outflows."
                    ),
                    evidence={
                        "operating_profit": format_money(operating_profit, currency),
                        "first_month_opening_cash": format_money(first.opening_cash, currency),
                        "last_month_closing_cash": format_money(last.closing_cash, currency),
                        "first_month_index": first.month_index,
                        "last_month_index": last.month_index,
                        "currency": currency,
                    },
                )
            )

    # --- 5. SHARP_DROP: month-over-month closing-cash fall > threshold -------
    for prev, curr in zip(points, points[1:]):
        if prev.closing_cash > ZERO:
            drop_ratio = (prev.closing_cash - curr.closing_cash) / prev.closing_cash
            if drop_ratio > cfg.sharp_drop_pct:
                alerts.append(
                    Alert(
                        code="SHARP_DROP",
                        severity=SEVERITY_INFO,
                        month=curr.month_index,
                        message=(
                            f"Closing cash fell {safe_div_str(prev.closing_cash - curr.closing_cash, prev.closing_cash, currency, places=4) or '>0'} "
                            f"from month {prev.month_index} to month {curr.month_index} "
                            f"({format_money(prev.closing_cash, currency)} → "
                            f"{format_money(curr.closing_cash, currency)})."
                        ),
                        evidence={
                            "month_index": curr.month_index,
                            "previous_month_index": prev.month_index,
                            "previous_closing_cash": format_money(prev.closing_cash, currency),
                            "current_closing_cash": format_money(curr.closing_cash, currency),
                            "drop_ratio": str(quantize(drop_ratio, currency)),
                            "sharp_drop_pct": str(cfg.sharp_drop_pct),
                            "currency": currency,
                        },
                    )
                )

    # Sort: critical first, then warning, then info; within a severity by month asc.
    alerts.sort(key=lambda a: (-_severity_rank(a.severity), a.month if a.month is not None else 0, a.code))
    return alerts


__all__ = [
    "MonthlyCashPoint",
    "AlertConfig",
    "Alert",
    "SEVERITY_CRITICAL",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    "ALL_SEVERITIES",
    "evaluate_alerts",
    "_build_monthly_points_from_totals",
]
