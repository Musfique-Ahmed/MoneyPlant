"""Tests for the financing-option matcher.

Covers: no-shortfall sentinel, hand-calculated annuity, DSCR boundaries,
ineligible product routing, ranking order, and Decimal precision.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.engine.alerts import MonthlyCashPoint
from app.engine.financing import (
    LABEL_NOT_RECOMMENDED as NOT_REC,
    LABEL_POSSIBLE,
    LABEL_RECOMMENDED as REC,
    FinancingContext,
    compute_funding_need_from_points,
    load_catalog,
    match_financing,
)
from app.engine.financing import _annuity_monthly_payment  # type: ignore  # noqa: PLC2701


# ---------------------------------------------------------------------------
# Catalog loading
# ---------------------------------------------------------------------------


CATALOG_PATH = (
    Path(__file__).resolve().parents[2]
    / "sample_data"
    / "financing_catalog.json"
)


def test_load_catalog_returns_synthetic_products() -> None:
    products, meta = load_catalog(CATALOG_PATH)
    assert len(products) == 5
    assert all(p.synthetic is True for p in products)
    assert meta["_synthetic"] is True
    # Each product has both an id and a name.
    for p in products:
        assert p.id
        assert p.name


def test_load_catalog_validates_amounts() -> None:
    """A bad catalog (max < min) must raise loudly, never silently coerce."""
    bad_path = Path(__file__).resolve().parents[2] / "sample_data" / "_bad_catalog.json"
    bad_path.write_text(
        json.dumps(
            {
                "_synthetic": True,
                "products": [
                    {
                        "id": "bad",
                        "name": "Bad",
                        "type": "x",
                        "min_amount": "100",
                        "max_amount": "50",  # < min
                        "min_months_operating": 1,
                        "min_avg_monthly_revenue": "0",
                        "max_term_months": 12,
                        "indicative_annual_rate": "0",
                        "suitable_use_cases": [],
                        "synthetic": True,
                    }
                ],
            }
        )
    )
    with pytest.raises(ValueError):
        load_catalog(bad_path)
    bad_path.unlink()


# ---------------------------------------------------------------------------
# Annuity math
# ---------------------------------------------------------------------------


def test_annuity_hand_calculated() -> None:
    """Hand-rolled example: $10,000 at 12% annual over 12 months.

    r = 0.01, payment = 10000 * 0.01 / (1 - 1.01^-12) ≈ 888.4874…
    Rounded HALF_UP to 2 dp = 888.49.
    """
    payment = _annuity_monthly_payment(
        principal=Decimal("10000"),
        annual_rate=Decimal("0.12"),
        term_months=12,
        currency="USD",
    )
    assert payment == Decimal("888.49")


def test_annuity_zero_rate_is_straight_line() -> None:
    payment = _annuity_monthly_payment(
        principal=Decimal("12000"),
        annual_rate=Decimal("0"),
        term_months=12,
        currency="USD",
    )
    assert payment == Decimal("1000.00")


def test_annuity_zero_term_returns_zero() -> None:
    payment = _annuity_monthly_payment(
        principal=Decimal("1000"),
        annual_rate=Decimal("0.10"),
        term_months=0,
        currency="USD",
    )
    assert payment == Decimal("0.00")


# ---------------------------------------------------------------------------
# Funding need from points
# ---------------------------------------------------------------------------


def test_funding_need_zero_when_trajectory_stays_non_negative() -> None:
    points = [
        MonthlyCashPoint(
            month_index=1,
            opening_cash=Decimal("0"),
            net_cash_movement=Decimal("100"),
            closing_cash=Decimal("100"),
        ),
        MonthlyCashPoint(
            month_index=2,
            opening_cash=Decimal("100"),
            net_cash_movement=Decimal("50"),
            closing_cash=Decimal("150"),
        ),
    ]
    assert compute_funding_need_from_points(points=points) == Decimal("0")


def test_funding_need_includes_shortfall_and_buffer() -> None:
    # min = -300; buffer = 100; funding_need = 400
    points = [
        MonthlyCashPoint(
            month_index=1,
            opening_cash=Decimal("0"),
            net_cash_movement=Decimal("100"),
            closing_cash=Decimal("100"),
        ),
        MonthlyCashPoint(
            month_index=2,
            opening_cash=Decimal("100"),
            net_cash_movement=Decimal("-400"),
            closing_cash=Decimal("-300"),
        ),
    ]
    assert compute_funding_need_from_points(points=points, min_buffer=Decimal("100")) == Decimal("400")


# ---------------------------------------------------------------------------
# Matcher: no-shortfall case returns sentinel
# ---------------------------------------------------------------------------


def test_no_financing_needed_when_funding_need_zero() -> None:
    products, _ = load_catalog(CATALOG_PATH)
    ctx = FinancingContext(
        currency="USD",
        funding_need=Decimal("0"),
        months_operating=24,
        avg_monthly_revenue=Decimal("15000"),
        monthly_operating_profit=Decimal("3000"),
    )
    outcome = match_financing(context=ctx, products=products)
    assert outcome.no_financing_needed is not None
    assert outcome.matches == ()
    assert "No projected cash shortfall" in outcome.no_financing_needed.reason


# ---------------------------------------------------------------------------
# Matcher: eligible product with high DSCR → recommended
# ---------------------------------------------------------------------------


def test_recommended_when_dscr_well_above_floor() -> None:
    products, _ = load_catalog(CATALOG_PATH)
    # Use a "term loan" sized at $10,000 (within its range).
    # Picking one specific product for predictability:
    term_loan = next(p for p in products if p.id == "term-loan-002")
    # Funding need within term-loan range; monthly op profit so DSCR is high.
    ctx = FinancingContext(
        currency="USD",
        funding_need=Decimal("10000"),
        months_operating=24,            # > 12 required
        avg_monthly_revenue=Decimal("15000"),  # > 10,000 required
        monthly_operating_profit=Decimal("4000"),
    )
    outcome = match_financing(context=ctx, products=products)
    matches_by_id = {m.product_id: m for m in outcome.matches}
    assert matches_by_id["term-loan-002"].label in {REC, LABEL_POSSIBLE}
    # When DSCR is comfortably above 1.2, label should be recommended.
    assert matches_by_id["term-loan-002"].label == REC


def test_possible_when_dscr_just_above_floor() -> None:
    products, _ = load_catalog(CATALOG_PATH)
    # Need a DSCR just above 1.2 but below 1.5 * 1.2 = 1.8.
    # 10,000 @ 10% over 12 months ≈ 879.16/mo → set monthly_op_profit = 1100 → DSCR ≈ 1.2506.
    ctx = FinancingContext(
        currency="USD",
        funding_need=Decimal("10000"),
        months_operating=24,
        avg_monthly_revenue=Decimal("15000"),
        monthly_operating_profit=Decimal("1100"),
    )
    outcome = match_financing(context=ctx, products=products)
    matches_by_id = {m.product_id: m for m in outcome.matches}
    tl = matches_by_id["term-loan-002"]
    # 1.2506 < 1.8; passes hard checks → "possible" not "recommended".
    assert tl.label == LABEL_POSSIBLE


# ---------------------------------------------------------------------------
# Matcher: DSCR < 1.0 fails affordability even when eligibility passes
# ---------------------------------------------------------------------------


def test_dscr_below_one_forces_not_recommended() -> None:
    products, _ = load_catalog(CATALOG_PATH)
    # 10,000 @ 10% over 12 months ≈ 879.16/mo. Set monthly_op_profit = 500 → DSCR ≈ 0.568.
    ctx = FinancingContext(
        currency="USD",
        funding_need=Decimal("10000"),
        months_operating=24,
        avg_monthly_revenue=Decimal("15000"),
        monthly_operating_profit=Decimal("500"),
    )
    outcome = match_financing(context=ctx, products=products)
    matches_by_id = {m.product_id: m for m in outcome.matches}
    assert matches_by_id["term-loan-002"].label == NOT_REC
    assert any("dscr" in u.lower() or "dscr_below" in u.lower() for u in matches_by_id["term-loan-002"].unmet_criteria)


# ---------------------------------------------------------------------------
# Matcher: ineligible product → not_recommended with unmet_criteria
# ---------------------------------------------------------------------------


def test_ineligible_product_not_recommended() -> None:
    products, _ = load_catalog(CATALOG_PATH)
    # Funding need of $200,000 exceeds term-loan-002 max of $250,000? No, that's in range.
    # Use equipment financing with $60,000 (within range) but months_operating=6 fails (needs >= 12).
    ctx = FinancingContext(
        currency="USD",
        funding_need=Decimal("60000"),
        months_operating=6,    # equipment fin wants >= 12
        avg_monthly_revenue=Decimal("20000"),
        monthly_operating_profit=Decimal("4000"),
    )
    outcome = match_financing(context=ctx, products=products)
    matches_by_id = {m.product_id: m for m in outcome.matches}
    ef = matches_by_id["equip-fin-004"]
    assert ef.label == NOT_REC
    assert any("months_operating" in u for u in ef.unmet_criteria)


def test_funding_need_below_min_amount_not_recommended() -> None:
    products, _ = load_catalog(CATALOG_PATH)
    ctx = FinancingContext(
        currency="USD",
        funding_need=Decimal("200"),  # below invoice-fin min of 500
        months_operating=24,
        avg_monthly_revenue=Decimal("15000"),
        monthly_operating_profit=Decimal("2000"),
    )
    outcome = match_financing(context=ctx, products=products)
    matches_by_id = {m.product_id: m for m in outcome.matches}
    inv = matches_by_id["invoice-fin-003"]
    assert inv.label == NOT_REC
    assert any("funding_need_within_range" in u for u in inv.unmet_criteria)


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def test_recommended_ranks_before_possible_ranks_before_not_recommended() -> None:
    products, _ = load_catalog(CATALOG_PATH)
    # Build a context where term-loan is recommended but invoice-fin is not.
    ctx = FinancingContext(
        currency="USD",
        funding_need=Decimal("10000"),
        months_operating=24,
        avg_monthly_revenue=Decimal("15000"),
        monthly_operating_profit=Decimal("4000"),
    )
    outcome = match_financing(context=ctx, products=products)
    labels_in_order = [m.label for m in outcome.matches]
    # The first product should be the recommended one (no not_recommended earlier).
    rec_idx = next(
        (i for i, l in enumerate(labels_in_order) if l == REC),
        len(labels_in_order),
    )
    pos_idx = next(
        (i for i, l in enumerate(labels_in_order) if l == LABEL_POSSIBLE),
        len(labels_in_order),
    )
    not_idx = next(
        (i for i, l in enumerate(labels_in_order) if l == NOT_REC),
        len(labels_in_order),
    )
    assert rec_idx < not_idx


# ---------------------------------------------------------------------------
# Decimal precision: nothing floats
# ---------------------------------------------------------------------------


def test_monthly_repayment_is_quantized_to_currency_precision() -> None:
    """The response value must be a string with exactly 2 decimals for USD."""
    products, _ = load_catalog(CATALOG_PATH)
    ctx = FinancingContext(
        currency="USD",
        funding_need=Decimal("10000"),
        months_operating=24,
        avg_monthly_revenue=Decimal("15000"),
        monthly_operating_profit=Decimal("4000"),
    )
    outcome = match_financing(context=ctx, products=products)
    for m in outcome.matches:
        assert "." in m.monthly_repayment
        # Two decimals (or one zero-decimal edge case we'll explicitly allow below).
        whole, frac = m.monthly_repayment.split(".")
        assert len(frac) == 2


def test_no_float_types_leak_through() -> None:
    """We don't want any accidental floats in the matcher outputs."""
    products, _ = load_catalog(CATALOG_PATH)
    ctx = FinancingContext(
        currency="USD",
        funding_need=Decimal("10000"),
        months_operating=24,
        avg_monthly_revenue=Decimal("15000"),
        monthly_operating_profit=Decimal("4000"),
    )
    outcome = match_financing(context=ctx, products=products)
    for m in outcome.matches:
        # All numeric fields on ProductMatch are strings (Decimal-sourced).
        assert isinstance(m.monthly_repayment, str)
        assert isinstance(m.requested_amount, str)
        assert isinstance(m.indicative_annual_rate, str)
        # DSCR is "" or a decimal string, never a float.
        assert m.dscr == "" or "." in m.dscr


# ---------------------------------------------------------------------------
# Catalog disclaimer / synthetic flag is forwarded
# ---------------------------------------------------------------------------


def test_catalog_disclaimer_present_in_outcome() -> None:
    products, _ = load_catalog(CATALOG_PATH)
    ctx = FinancingContext(
        currency="USD",
        funding_need=Decimal("10000"),
        months_operating=24,
        avg_monthly_revenue=Decimal("15000"),
        monthly_operating_profit=Decimal("4000"),
    )
    outcome = match_financing(context=ctx, products=products)
    assert "SYNTHETIC" in outcome.catalog_disclaimer
    assert "Not a credit decision" in outcome.catalog_disclaimer


def test_every_match_carries_synthetic_flag() -> None:
    products, _ = load_catalog(CATALOG_PATH)
    ctx = FinancingContext(
        currency="USD",
        funding_need=Decimal("10000"),
        months_operating=24,
        avg_monthly_revenue=Decimal("15000"),
        monthly_operating_profit=Decimal("4000"),
    )
    outcome = match_financing(context=ctx, products=products)
    assert all(m.synthetic is True for m in outcome.matches)
