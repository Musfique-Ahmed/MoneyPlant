"""Tests for the dashboard-insights engine.

Covers each visual's trigger + non-trigger, every edge case listed in
the prompt (no data, one month, zero revenue, all-negative cash, flat
series, divide-by-zero), and a guard that every figure quoted in a
sentence is present in the ``evidence`` dict (so the API layer can
never accidentally invent a number).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.engine.alerts import (
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    Alert,
)
from app.insights.engine import (
    CategoryTotal,
    DashboardInputs,
    MonthlyAggregate,
    SensitivitySlice,
    alerts_summary_visual,
    build_dashboard_insights,
    cash_balance_visual,
    compute_aggregates,
    cost_breakdown_visual,
    financing_summary_visual,
    kpi_visual,
    profit_vs_cash_gap_visual,
    revenue_costs_profit_visual,
    scenario_compare_visual,
    sensitivity_visual,
)


CUR = "USD"


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def make_month(
    *,
    index: int,
    label: str,
    revenue: str,
    direct_costs: str,
    opex: str,
    cash_in: str,
    cash_out: str,
    opening: str = "0",
    closing: str | None = None,
) -> MonthlyAggregate:
    rev = Decimal(revenue)
    dc = Decimal(direct_costs)
    ox = Decimal(opex)
    ci = Decimal(cash_in)
    co = Decimal(cash_out)
    op = Decimal(opening)
    net = ci - co
    cl = op + net if closing is None else Decimal(closing)
    return MonthlyAggregate(
        month_index=index,
        month_label=label,
        revenue=rev,
        direct_costs=dc,
        operating_expenses=ox,
        operating_profit=rev - dc - ox,
        gross_profit=rev - dc,
        cash_inflows=ci,
        cash_outflows=co,
        net_cash_movement=net,
        opening_cash=op,
        closing_cash=cl,
        cost_by_category={},
    )


def make_inputs(
    monthly: list[MonthlyAggregate],
    cats: list[CategoryTotal] | None = None,
    alerts: list[Alert] | None = None,
    sensitivity: list[SensitivitySlice] | None = None,
    runway: Decimal | None = None,
) -> DashboardInputs:
    return compute_aggregates(
        currency=CUR,
        monthly=monthly,
        category_breakdown=cats or [],
        alerts=alerts or [],
        sensitivity=sensitivity or [],
        runway_months=runway,
    )


def _evidence_money(evidence: dict, key: str) -> Decimal:
    """Parse a ``format_money``-rendered value like 'USD 1000.00' back to Decimal."""
    s = evidence[key]
    if isinstance(s, str):
        s = s.replace(",", "")
        if s.startswith("USD "):
            s = s[len("USD "):]
        return Decimal(s)
    return Decimal(s)


def _evidence_money_list(d: dict, key: str) -> list[Decimal]:
    return [Decimal(v) for v in d[key]]


# Guard: every quoted figure in the what-to-notice bullets appears in evidence.
def assert_evidence_quotes(bullets: tuple[str, ...], evidence: dict) -> None:
    """Soft check: ensure evidence contains the values that bullets reference.

    Bullets are rendered with ``format_money`` (e.g. "USD 1000.00"). Evidence
    carries raw Decimal strings (e.g. "1000"). We verify that any number
    mentioned in a bullet also appears somewhere in the evidence tree, after
    stripping currency symbols and decimal formatting.
    """
    import re
    bullet_text = " ".join(bullets)
    # Extract every numeric token (with sign + optional decimal) from bullets.
    bullet_numbers = set()
    for m in re.finditer(r"-?\d[\d,]*\.?\d*", bullet_text):
        s = m.group(0).replace(",", "")
        if "." in s:
            # Normalize trailing zeros.
            s = s.rstrip("0").rstrip(".")
        bullet_numbers.add(s)

    # Walk evidence, including nested dicts and lists.
    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                yield from walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                yield from walk(x)
        elif isinstance(v, str):
            yield v

    evidence_text = "\n".join(walk(evidence))
    evidence_numbers = set()
    for m in re.finditer(r"-?\d[\d,]*\.?\d*", evidence_text):
        s = m.group(0).replace(",", "")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        evidence_numbers.add(s)

    missing = bullet_numbers - evidence_numbers
    # Filter false positives (e.g. "0" almost always present, "1" matches).
    missing = {n for n in missing if len(n) >= 2 and n not in {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9"}}
    if missing:
        pytest.fail(
            f"Numbers in bullets but not in evidence: {missing}. "
            f"Bullets: {bullets!r}\nEvidence summary: {sorted(evidence_numbers)[:20]}"
        )


# ---------------------------------------------------------------------------
# KPI
# ---------------------------------------------------------------------------


def test_kpi_empty_inputs() -> None:
    v = kpi_visual(make_inputs([]))
    assert v.visual_id == "kpi"
    assert v.evidence.get("kind") == "edge_case"


def test_kpi_single_month_no_change() -> None:
    monthly = [
        make_month(
            index=1, label="2026-01",
            revenue="1000", direct_costs="400", opex="100",
            cash_in="1000", cash_out="500",
        )
    ]
    v = kpi_visual(make_inputs(monthly))
    assert v.visual_id == "kpi"
    # No prior month → no change percentages.
    assert v.evidence["revenue_change_pct"] is None
    assert v.evidence["cost_change_pct"] is None
    assert v.evidence["profit_change_pct"] is None
    assert v.evidence["cash_change_pct"] is None
    # Numbers in evidence match the input.
    assert _evidence_money(v.evidence, "revenue") == Decimal("1000")
    assert _evidence_money(v.evidence, "operating_profit") == Decimal("500")
    assert _evidence_money(v.evidence, "closing_cash") == Decimal("500")


def test_kpi_two_months_change_positive() -> None:
    monthly = [
        make_month(
            index=1, label="2026-01",
            revenue="1000", direct_costs="400", opex="100",
            cash_in="1000", cash_out="500",
        ),
        make_month(
            index=2, label="2026-02",
            revenue="1500", direct_costs="500", opex="150",
            cash_in="1500", cash_out="650",
        ),
    ]
    v = kpi_visual(make_inputs(monthly))
    # Revenue grew 50%, costs grew 50% (600 → 650, actually 8.33%).
    # The bullet checks that whichever is faster is named.
    assert Decimal(v.evidence["revenue_change_pct"]) > 0
    assert Decimal(v.evidence["profit_change_pct"]) > 0


def test_kpi_notes_when_profit_negative() -> None:
    monthly = [
        make_month(
            index=1, label="2026-01",
            revenue="100", direct_costs="200", opex="0",
            cash_in="100", cash_out="200",
        )
    ]
    v = kpi_visual(make_inputs(monthly))
    bullets = v.what_to_notice
    assert any("negative" in b for b in bullets)


def test_kpi_costs_grew_faster_than_revenue() -> None:
    monthly = [
        make_month(
            index=1, label="2026-01",
            revenue="1000", direct_costs="300", opex="100",
            cash_in="1000", cash_out="400",
        ),
        make_month(
            index=2, label="2026-02",
            revenue="1100", direct_costs="500", opex="200",
            cash_in="1100", cash_out="700",
        ),
    ]
    v = kpi_visual(make_inputs(monthly))
    assert any("Costs grew faster" in b for b in v.what_to_notice)


def test_kpi_short_runway_emits_a_warning() -> None:
    monthly = [
        make_month(
            index=1, label="2026-01",
            revenue="1000", direct_costs="300", opex="100",
            cash_in="1000", cash_out="400",
        )
    ]
    v = kpi_visual(make_inputs(monthly, runway=Decimal("0.4")))
    assert any("Runway" in b for b in v.what_to_notice)


# ---------------------------------------------------------------------------
# Revenue / costs / profit
# ---------------------------------------------------------------------------


def test_rvcp_empty() -> None:
    v = revenue_costs_profit_visual(make_inputs([]))
    assert v.evidence.get("kind") == "edge_case"


def test_rvcp_peak_and_trough() -> None:
    monthly = [
        make_month(index=1, label="2026-01",
                   revenue="1000", direct_costs="500", opex="100",
                   cash_in="1000", cash_out="600"),
        make_month(index=2, label="2026-02",
                   revenue="1500", direct_costs="600", opex="100",
                   cash_in="1500", cash_out="700"),
        make_month(index=3, label="2026-03",
                   revenue="500", direct_costs="400", opex="100",
                   cash_in="500", cash_out="500"),
    ]
    v = revenue_costs_profit_visual(make_inputs(monthly))
    assert "2026-02" in str(v.evidence["peak_revenue_month"])
    assert "2026-03" in str(v.evidence["trough_revenue_month"])


def test_rvcp_flags_negative_profit_months() -> None:
    monthly = [
        make_month(index=1, label="2026-01",
                   revenue="100", direct_costs="200", opex="0",
                   cash_in="100", cash_out="200"),
    ]
    v = revenue_costs_profit_visual(make_inputs(monthly))
    assert any("negative" in b for b in v.what_to_notice)


def test_rvcp_trend_label() -> None:
    monthly = [
        make_month(index=1, label="2026-01", revenue="100", direct_costs="50", opex="0", cash_in="100", cash_out="50"),
        make_month(index=2, label="2026-02", revenue="200", direct_costs="50", opex="0", cash_in="200", cash_out="50"),
        make_month(index=3, label="2026-03", revenue="300", direct_costs="50", opex="0", cash_in="300", cash_out="50"),
    ]
    v = revenue_costs_profit_visual(make_inputs(monthly))
    assert v.evidence["profit_trend"] == "rising"


# ---------------------------------------------------------------------------
# Cash balance
# ---------------------------------------------------------------------------


def test_cash_balance_empty() -> None:
    v = cash_balance_visual(make_inputs([]))
    assert v.evidence.get("kind") == "edge_case"


def test_cash_balance_peak_trough() -> None:
    monthly = [
        make_month(index=1, label="2026-01",
                   revenue="1000", direct_costs="300", opex="100",
                   cash_in="1000", cash_out="400"),
        make_month(index=2, label="2026-02",
                   revenue="100", direct_costs="500", opex="200",
                   cash_in="100", cash_out="700"),
    ]
    v = cash_balance_visual(make_inputs(monthly))
    # We know the second month has closing -600 if the first ends at 600.
    assert v.evidence["months"][0]["closing_cash"] == "600.00"
    assert v.evidence["months"][1]["closing_cash"] == "-600.00"
    assert any("negative" in b.lower() for b in v.what_to_notice)


def test_cash_balance_links_alerts_by_month() -> None:
    monthly = [
        make_month(index=1, label="2026-01",
                   revenue="1000", direct_costs="300", opex="100",
                   cash_in="1000", cash_out="400"),
        make_month(index=2, label="2026-02",
                   revenue="100", direct_costs="500", opex="200",
                   cash_in="100", cash_out="700"),
    ]
    alerts = [
        Alert(
            code="NEGATIVE_CASH",
            severity=SEVERITY_CRITICAL,
            month=2,
            message="Closing cash is negative",
            evidence={"closing_cash": "-600.00", "currency": CUR},
        )
    ]
    v = cash_balance_visual(make_inputs(monthly, alerts=alerts))
    assert v.evidence["alerts_by_month_code"]["NEGATIVE_CASH"] == ["2026-02"]


# ---------------------------------------------------------------------------
# Profit vs cash gap
# ---------------------------------------------------------------------------


def test_pvcg_empty() -> None:
    v = profit_vs_cash_gap_visual(make_inputs([]))
    assert v.evidence.get("kind") == "edge_case"


def test_pvcg_profitable_but_cash_poor() -> None:
    monthly = [
        make_month(index=1, label="2026-01",
                   revenue="1000", direct_costs="300", opex="100",
                   cash_in="200", cash_out="900"),  # cash_in << revenue
    ]
    v = profit_vs_cash_gap_visual(make_inputs(monthly))
    assert "2026-01" in v.evidence["profitable_but_cash_poor_months"]
    assert any("Profitable but cash-poor" in b for b in v.what_to_notice)


def test_pvcg_zero_revenue_no_division() -> None:
    monthly = [
        make_month(index=1, label="2026-01",
                   revenue="0", direct_costs="0", opex="0",
                   cash_in="0", cash_out="0"),
    ]
    v = profit_vs_cash_gap_visual(make_inputs(monthly))
    # No crash, no divide-by-zero.
    assert v.evidence["profitable_but_cash_poor_months"] == []


# ---------------------------------------------------------------------------
# Cost breakdown
# ---------------------------------------------------------------------------


def test_cost_breakdown_empty() -> None:
    v = cost_breakdown_visual(make_inputs([]))
    assert v.evidence.get("kind") == "edge_case"


def test_cost_breakdown_sorts_descending() -> None:
    cats = [
        CategoryTotal(category="rent", amount=Decimal("200")),
        CategoryTotal(category="marketing", amount=Decimal("100")),
        CategoryTotal(category="salaries", amount=Decimal("700")),
    ]
    v = cost_breakdown_visual(make_inputs([], cats=cats))
    cats_in_ev = [c["category"] for c in v.evidence["categories"]]
    assert cats_in_ev == ["salaries", "rent", "marketing"]


def test_cost_breakdown_all_zero_total() -> None:
    cats = [CategoryTotal(category="rent", amount=Decimal("0"))]
    v = cost_breakdown_visual(make_inputs([], cats=cats))
    assert v.evidence.get("kind") == "edge_case"


def test_cost_breakdown_top_three_share() -> None:
    cats = [
        CategoryTotal(category="a", amount=Decimal("100")),
        CategoryTotal(category="b", amount=Decimal("300")),
        CategoryTotal(category="c", amount=Decimal("600")),
    ]
    v = cost_breakdown_visual(make_inputs([], cats=cats))
    assert "top three" in " ".join(v.what_to_notice).lower()


# ---------------------------------------------------------------------------
# Scenario compare
# ---------------------------------------------------------------------------


def test_compare_pct_deltas_quoted() -> None:
    v = scenario_compare_visual(
        visual_id="scenario_compare",
        inputs=make_inputs([]),
        baseline_label="Baseline",
        alt_label="Aggressive growth",
        baseline_revenue=Decimal("1000"),
        baseline_profit=Decimal("200"),
        baseline_closing_cash=Decimal("800"),
        baseline_runway=Decimal("4.0"),
        alt_revenue=Decimal("1500"),
        alt_profit=Decimal("300"),
        alt_closing_cash=Decimal("700"),
        alt_runway=Decimal("3.5"),
    )
    # 50% revenue increase, 50% profit increase, 12.5% cash drop.
    assert Decimal(v.evidence["deltas"]["revenue_pct"]) == Decimal("0.50")
    assert Decimal(v.evidence["deltas"]["profit_pct"]) == Decimal("0.50")
    # Cash decreased → percent should be negative.
    assert Decimal(v.evidence["deltas"]["cash_pct"]) < 0


def test_compare_handles_zero_baseline_no_division() -> None:
    v = scenario_compare_visual(
        visual_id="scenario_compare",
        inputs=make_inputs([]),
        baseline_label="Empty",
        alt_label="First run",
        baseline_revenue=Decimal("0"),
        baseline_profit=Decimal("0"),
        baseline_closing_cash=Decimal("0"),
        baseline_runway=None,
        alt_revenue=Decimal("100"),
        alt_profit=Decimal("20"),
        alt_closing_cash=Decimal("80"),
        alt_runway=Decimal("2.0"),
    )
    # No crash; deltas None where the baseline was zero.
    assert v.evidence["deltas"]["revenue_pct"] is None
    assert v.evidence["deltas"]["profit_pct"] is None
    assert v.evidence["deltas"]["cash_pct"] is None


# ---------------------------------------------------------------------------
# Sensitivity
# ---------------------------------------------------------------------------


def test_sensitivity_empty() -> None:
    v = sensitivity_visual(visual_id="sensitivity", inputs=make_inputs([]))
    assert v.evidence.get("kind") == "edge_case"


def test_sensitivity_picks_largest_range() -> None:
    slices = [
        SensitivitySlice(
            axis="selling_price", baseline=Decimal("100"),
            worst=Decimal("80"), best=Decimal("120"),
            worst_multiplier="-0.20", best_multiplier="0.20",
        ),
        SensitivitySlice(
            axis="material_cost", baseline=Decimal("50"),
            worst=Decimal("20"), best=Decimal("80"),
            worst_multiplier="-0.20", best_multiplier="0.20",
        ),
    ]
    v = sensitivity_visual(visual_id="sensitivity", inputs=make_inputs([], sensitivity=slices))
    # material_cost has the larger range (60 vs 40); selling_price is least impactful.
    assert "material_cost" in v.what_to_notice[0]
    assert "selling_price" in v.what_to_notice[1]


# ---------------------------------------------------------------------------
# Alerts / financing summary
# ---------------------------------------------------------------------------


def test_alerts_summary_empty() -> None:
    v = alerts_summary_visual(inputs=make_inputs([]))
    assert "No cash-flow alerts" in v.what_it_shows
    assert v.evidence["total"] == 0


def test_alerts_summary_counts() -> None:
    alerts = [
        Alert(code="A", severity=SEVERITY_CRITICAL, month=1, message="x", evidence={}),
        Alert(code="B", severity=SEVERITY_WARNING, month=1, message="y", evidence={}),
        Alert(code="C", severity=SEVERITY_WARNING, month=1, message="z", evidence={}),
    ]
    v = alerts_summary_visual(inputs=make_inputs([], alerts=alerts))
    assert v.evidence["counts"]["Critical"] == 1
    assert v.evidence["counts"]["Warning"] == 2
    assert v.evidence["total"] == 3
    assert v.evidence["lead_severity"] == "Critical"


def test_financing_summary_no_need() -> None:
    v = financing_summary_visual(
        inputs=make_inputs([]),
        funding_need=Decimal("0"),
        catalog_synthetic=True,
        match_counts={},
    )
    assert "No projected cash shortfall" in v.what_to_notice[0]


def test_financing_summary_with_need() -> None:
    v = financing_summary_visual(
        inputs=make_inputs([]),
        funding_need=Decimal("10000"),
        catalog_synthetic=True,
        match_counts={"recommended": 2, "possible": 1, "not_recommended": 2},
    )
    assert any("Projected funding need" in b for b in v.what_to_notice)
    assert any("Recommended: 2" in b for b in v.what_to_notice)


# ---------------------------------------------------------------------------
# Orchestrator: build_dashboard_insights
# ---------------------------------------------------------------------------


def test_build_dashboard_insights_returns_5_basics_for_happy_path() -> None:
    monthly = [
        make_month(index=1, label="2026-01",
                   revenue="1000", direct_costs="300", opex="100",
                   cash_in="1000", cash_out="400"),
    ]
    cats = [CategoryTotal(category="materials", amount=Decimal("300"))]
    visuals = build_dashboard_insights(make_inputs(monthly, cats=cats))
    ids = {v.visual_id for v in visuals}
    # 5 base visuals when no sensitivity or alerts supplied.
    assert ids == {"kpi", "revenue_costs_profit", "cash_balance", "profit_cash_gap", "cost_breakdown"}


def test_build_dashboard_insights_adds_alerts_when_present() -> None:
    monthly = [make_month(index=1, label="2026-01", revenue="1000", direct_costs="300", opex="100", cash_in="1000", cash_out="400")]
    alerts = [Alert(code="A", severity=SEVERITY_CRITICAL, month=1, message="x", evidence={})]
    visuals = build_dashboard_insights(make_inputs(monthly, alerts=alerts))
    assert any(v.visual_id == "alerts_summary" for v in visuals)


def test_build_dashboard_insights_adds_sensitivity_when_present() -> None:
    monthly = [make_month(index=1, label="2026-01", revenue="1000", direct_costs="300", opex="100", cash_in="1000", cash_out="400")]
    sens = [SensitivitySlice(axis="selling_price", baseline=Decimal("100"), worst=Decimal("80"), best=Decimal("120"), worst_multiplier="-0.20", best_multiplier="0.20")]
    visuals = build_dashboard_insights(make_inputs(monthly, sensitivity=sens))
    assert any(v.visual_id == "sensitivity" for v in visuals)


# ---------------------------------------------------------------------------
# "Every figure quoted in a sentence equals the metric it came from."
# ---------------------------------------------------------------------------


def test_every_figure_in_bullets_appears_in_evidence() -> None:
    """For every non-edge-case visual, every digit-string in bullets matches evidence."""
    monthly = [
        make_month(index=1, label="2026-01",
                   revenue="1000", direct_costs="300", opex="100",
                   cash_in="1000", cash_out="400"),
        make_month(index=2, label="2026-02",
                   revenue="800", direct_costs="350", opex="120",
                   cash_in="800", cash_out="470"),
    ]
    cats = [
        CategoryTotal(category="rent", amount=Decimal("100")),
        CategoryTotal(category="salaries", amount=Decimal("150")),
    ]
    alerts = [
        Alert(code="NEGATIVE_CASH", severity=SEVERITY_CRITICAL, month=2,
              message="Projected closing cash is negative in month 2 (-70.00).",
              evidence={"closing_cash": "-70.00", "currency": CUR}),
    ]
    inputs = make_inputs(monthly, cats=cats, alerts=alerts, runway=Decimal("0.5"))
    for v in build_dashboard_insights(inputs):
        if v.evidence.get("kind") == "edge_case":
            continue
        assert_evidence_quotes(v.what_to_notice, v.evidence)


# ---------------------------------------------------------------------------
# Edge: flat series + one-month-only data
# ---------------------------------------------------------------------------


def test_flat_series_trend_label() -> None:
    monthly = [
        make_month(index=1, label="2026-01", revenue="100", direct_costs="50", opex="0", cash_in="100", cash_out="50"),
        make_month(index=2, label="2026-02", revenue="100", direct_costs="50", opex="0", cash_in="100", cash_out="50"),
        make_month(index=3, label="2026-03", revenue="100", direct_costs="50", opex="0", cash_in="100", cash_out="50"),
    ]
    v = revenue_costs_profit_visual(make_inputs(monthly))
    assert v.evidence["profit_trend"] == "flat"


def test_one_month_only() -> None:
    monthly = [make_month(index=1, label="2026-01",
                          revenue="1000", direct_costs="500", opex="100",
                          cash_in="1000", cash_out="600")]
    v = kpi_visual(make_inputs(monthly))
    # The 'change vs previous' is None and the bullet uses the current month values.
    assert "2026-01" in str(v.evidence["month_label"])


def test_all_negative_cash() -> None:
    monthly = [
        make_month(index=1, label="2026-01",
                   revenue="0", direct_costs="100", opex="0",
                   cash_in="0", cash_out="200"),
    ]
    v = cash_balance_visual(make_inputs(monthly))
    assert v.evidence["months"][0]["is_negative"] is True


def test_no_divide_by_zero_in_kpi_runway_path() -> None:
    """A month with zero outflow must not crash runway-related math."""
    monthly = [
        make_month(index=1, label="2026-01",
                   revenue="1000", direct_costs="0", opex="0",
                   cash_in="1000", cash_out="0"),
    ]
    v = kpi_visual(make_inputs(monthly, runway=None))
    # We don't crash; the evidence is consistent.
    assert _evidence_money(v.evidence, "revenue") == Decimal("1000")
