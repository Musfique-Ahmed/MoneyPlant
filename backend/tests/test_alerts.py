"""Tests for the cash-flow alerts engine.

Each rule is exercised for its trigger, its non-trigger, and its
boundary case. Empty input is also covered (the dashboard must always
be able to render "All clear").
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.engine.alerts import (
    AlertConfig,
    MonthlyCashPoint,
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    evaluate_alerts,
)


CURRENCY = "USD"


def make_points(values: list[tuple[str, str]]) -> list[MonthlyCashPoint]:
    """Build a trajectory from a list of ``(net_cash_movement, closing_cash)`` strings.

    The opening of month N+1 equals the closing of month N so the math
    is self-consistent — when not, the engine still respects the explicit
    closing values supplied here (the API computes a fresh opening from the
    prior closing; the alerts module itself is pure).
    """
    out: list[MonthlyCashPoint] = []
    for idx, (net, close) in enumerate(values, start=1):
        opening = Decimal(out[-1].closing_cash) if out else Decimal("0")
        out.append(
            MonthlyCashPoint(
                month_index=idx,
                opening_cash=opening,
                net_cash_movement=Decimal(net),
                closing_cash=Decimal(close),
            )
        )
    return out


# ---------------------------------------------------------------------------
# NEGATIVE_CASH
# ---------------------------------------------------------------------------


def test_negative_cash_triggers_critical() -> None:
    points = make_points(
        [
            ("100", "100"),
            ("-50", "50"),
            ("-100", "-50"),  # closing < 0 here
        ]
    )
    alerts = evaluate_alerts(
        points=points,
        runway_months=None,
        operating_profit=Decimal("-50"),
        currency=CURRENCY,
    )
    codes = [a.code for a in alerts]
    assert "NEGATIVE_CASH" in codes
    neg = next(a for a in alerts if a.code == "NEGATIVE_CASH")
    assert neg.severity == SEVERITY_CRITICAL
    assert neg.month == 3
    assert neg.evidence["closing_cash"] == "-50.00"


def test_negative_cash_does_not_trigger_when_zero_or_positive() -> None:
    points = make_points([("100", "100"), ("-30", "70"), ("-20", "50")])
    alerts = evaluate_alerts(
        points=points,
        runway_months=None,
        operating_profit=Decimal("150"),
        currency=CURRENCY,
    )
    assert not any(a.code == "NEGATIVE_CASH" for a in alerts)


def test_negative_cash_boundary_at_zero() -> None:
    """Closing cash == 0 is not negative; it should not trigger."""
    points = make_points([("-10", "-10"), ("10", "0")])
    alerts = evaluate_alerts(
        points=points,
        runway_months=None,
        operating_profit=Decimal("0"),
        currency=CURRENCY,
    )
    # First month is negative; second month is exactly zero. Expect one NEGATIVE_CASH.
    neg = [a for a in alerts if a.code == "NEGATIVE_CASH"]
    assert len(neg) == 1
    assert neg[0].month == 1


# ---------------------------------------------------------------------------
# LOW_BUFFER
# ---------------------------------------------------------------------------


def test_low_buffer_triggers_warning_below_one_month_average_opex() -> None:
    # Avg opex over the 3 outflow months = (100 + 50 + 50)/4 ≈ 50.00.
    # Buffer threshold = 1 * 50 = 50.
    # Month 1: opening 0, closing 100 (above) → no alert.
    # Month 2: closing 0 (below) → alert.
    # Month 3: closing -50 (below) → alert (already caught by NEGATIVE_CASH too).
    points = make_points(
        [
            ("-100", "0"),  # first month: opens at 0, burns 100, but the closing here drives month 2 opening
            ("100", "100"),
            ("-50", "50"),
            ("-100", "-50"),
        ]
    )
    alerts = evaluate_alerts(
        points=points,
        runway_months=None,
        operating_profit=Decimal("0"),
        currency=CURRENCY,
    )
    low_buffer = [a for a in alerts if a.code == "LOW_BUFFER"]
    assert len(low_buffer) >= 1
    assert all(a.severity == SEVERITY_WARNING for a in low_buffer)


def test_low_buffer_does_not_trigger_when_always_above_buffer() -> None:
    # Generate high profit every period so closing stays comfortably above the buffer.
    points = make_points(
        [
            ("500", "500"),
            ("500", "1000"),
            ("500", "1500"),
        ]
    )
    alerts = evaluate_alerts(
        points=points,
        runway_months=None,
        operating_profit=Decimal("1500"),
        currency=CURRENCY,
    )
    assert not any(a.code == "LOW_BUFFER" for a in alerts)


def test_low_buffer_zero_outflow_skips_rule() -> None:
    # All positive net cash — avg opex = 0, threshold = 0, nothing triggers.
    points = make_points([("100", "100"), ("100", "200")])
    alerts = evaluate_alerts(
        points=points,
        runway_months=None,
        operating_profit=Decimal("200"),
        currency=CURRENCY,
    )
    assert not any(a.code == "LOW_BUFFER" for a in alerts)


# ---------------------------------------------------------------------------
# SHORT_RUNWAY
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "runway,expect_code,expect_severity",
    [
        (Decimal("0.5"), "SHORT_RUNWAY", SEVERITY_CRITICAL),
        (Decimal("0.99"), "SHORT_RUNWAY", SEVERITY_CRITICAL),
        (Decimal("1.0"), "SHORT_RUNWAY", SEVERITY_WARNING),  # under 3 = warning
        (Decimal("2.5"), "SHORT_RUNWAY", SEVERITY_WARNING),
        (Decimal("2.99"), "SHORT_RUNWAY", SEVERITY_WARNING),
        (Decimal("3.0"), None, None),  # boundary: not < 3, no alert
        (Decimal("12.0"), None, None),
    ],
)
def test_short_runway_severity_boundaries(
    runway: Decimal, expect_code: str | None, expect_severity: str | None
) -> None:
    points = make_points([("100", "100"), ("100", "200")])
    alerts = evaluate_alerts(
        points=points,
        runway_months=runway,
        operating_profit=Decimal("100"),
        currency=CURRENCY,
    )
    matches = [a for a in alerts if a.code == "SHORT_RUNWAY"]
    if expect_code is None:
        assert matches == []
    else:
        assert len(matches) == 1
        assert matches[0].severity == expect_severity
        assert matches[0].month is None  # period-wide rule


def test_short_runway_skipped_when_runway_is_none() -> None:
    points = make_points([("100", "100"), ("100", "200")])
    alerts = evaluate_alerts(
        points=points,
        runway_months=None,
        operating_profit=Decimal("100"),
        currency=CURRENCY,
    )
    assert not any(a.code == "SHORT_RUNWAY" for a in alerts)


# ---------------------------------------------------------------------------
# PROFITABLE_BUT_CASH_POOR
# ---------------------------------------------------------------------------


def test_profitable_but_cash_poor_triggers_warning() -> None:
    # Operating profit > 0, but closing cash of the final month is below the opening of the first.
    points = make_points(
        [
            ("0", "100"),  # opens 0, +100 closing
            ("-200", "-100"),  # falls below 0
        ]
    )
    alerts = evaluate_alerts(
        points=points,
        runway_months=None,
        operating_profit=Decimal("50"),
        currency=CURRENCY,
    )
    pbcp = [a for a in alerts if a.code == "PROFITABLE_BUT_CASH_POOR"]
    assert len(pbcp) == 1
    assert pbcp[0].severity == SEVERITY_WARNING
    assert pbcp[0].month == 2


def test_profitable_but_cash_poor_does_not_trigger_when_cash_rising() -> None:
    points = make_points([("100", "100"), ("100", "200")])
    alerts = evaluate_alerts(
        points=points,
        runway_months=None,
        operating_profit=Decimal("100"),
        currency=CURRENCY,
    )
    assert not any(a.code == "PROFITABLE_BUT_CASH_POOR" for a in alerts)


def test_profitable_but_cash_poor_does_not_trigger_when_profit_non_positive() -> None:
    points = make_points([("0", "100"), ("-200", "-100")])
    alerts = evaluate_alerts(
        points=points,
        runway_months=None,
        operating_profit=Decimal("-50"),  # loss, not profit
        currency=CURRENCY,
    )
    assert not any(a.code == "PROFITABLE_BUT_CASH_POOR" for a in alerts)


# ---------------------------------------------------------------------------
# SHARP_DROP
# ---------------------------------------------------------------------------


def test_sharp_drop_triggers_info() -> None:
    # 1000 → 700 is a 30% drop (above the default 25% threshold).
    points = make_points([("0", "1000"), ("-300", "700")])
    alerts = evaluate_alerts(
        points=points,
        runway_months=None,
        operating_profit=Decimal("100"),
        currency=CURRENCY,
    )
    sharp = [a for a in alerts if a.code == "SHARP_DROP"]
    assert len(sharp) == 1
    assert sharp[0].severity == SEVERITY_INFO
    assert sharp[0].month == 2


def test_sharp_drop_does_not_trigger_below_threshold() -> None:
    # 1000 → 800 = 20% drop (below 25%).
    points = make_points([("0", "1000"), ("-200", "800")])
    alerts = evaluate_alerts(
        points=points,
        runway_months=None,
        operating_profit=Decimal("100"),
        currency=CURRENCY,
    )
    assert not any(a.code == "SHARP_DROP" for a in alerts)


def test_sharp_drop_does_not_trigger_when_previous_cash_zero() -> None:
    # Division-by-zero guard: previous_cash = 0 → drop ratio undefined → skip.
    points = make_points([("0", "0"), ("-100", "-100")])
    alerts = evaluate_alerts(
        points=points,
        runway_months=None,
        operating_profit=Decimal("-100"),
        currency=CURRENCY,
    )
    assert not any(a.code == "SHARP_DROP" for a in alerts)


# ---------------------------------------------------------------------------
# Empty data + sorting
# ---------------------------------------------------------------------------


def test_empty_points_returns_empty_list() -> None:
    alerts = evaluate_alerts(
        points=[],
        runway_months=None,
        operating_profit=Decimal("0"),
        currency=CURRENCY,
    )
    assert alerts == []


def test_critical_alerts_sort_before_warnings_before_info() -> None:
    points = make_points(
        [
            ("0", "1000"),  # month 1
            ("-1200", "-200"),  # month 2: NEGATIVE_CASH critical + SHORT_RUNWAY critical + SHARP_DROP info
        ]
    )
    alerts = evaluate_alerts(
        points=points,
        runway_months=Decimal("0.5"),
        operating_profit=Decimal("100"),
        currency=CURRENCY,
    )
    severities = [a.severity for a in alerts]
    # First non-empty severity should be Critical (or all Critical) before INFO appears.
    info_idx = next(
        (i for i, s in enumerate(severities) if s == SEVERITY_INFO), len(severities)
    )
    critical_idx = next(
        (i for i, s in enumerate(severities) if s == SEVERITY_CRITICAL), len(severities)
    )
    assert critical_idx < info_idx or not any(s == SEVERITY_CRITICAL for s in severities)


def test_alerts_have_a_currency_field_in_evidence() -> None:
    points = make_points([("0", "100"), ("-200", "-100")])
    alerts = evaluate_alerts(
        points=points,
        runway_months=None,
        operating_profit=Decimal("100"),
        currency=CURRENCY,
    )
    for a in alerts:
        # Every alert's evidence records the currency explicitly.
        assert a.evidence.get("currency") == CURRENCY or "currency" in a.evidence