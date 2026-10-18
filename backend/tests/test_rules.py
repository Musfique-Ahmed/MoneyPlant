"""Rule engine tests.

The rule engine has two contracts that MUST hold:

1. Each rule function returns a :class:`RuleEvaluation` matching the schema.
2. ``aggregate_status`` enforces hard-constraint precedence: a single hard
   ``breached`` rule forces ``reject`` regardless of any other votes.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from app.schemas.business import BusinessRead, Industry, Currency
from app.schemas.decision import (
    OverallStatus,
    RuleSeverity,
    RuleStatus,
)
from app.schemas.finance import ScenarioResult
from app.services.rules.engine import (
    aggregate_status,
    evaluate_rules,
)


def _business(
    *,
    min_cash_reserve: str = "0",
    target_operating_margin: str = "0.10",
    max_unsold_inventory_exposure_pct: str = "0.20",
) -> BusinessRead:
    now = datetime(2026, 1, 1, 0, 0, 0)
    return BusinessRead(
        id="biz-1",
        name="Acme",
        industry=Industry.MANUFACTURING,
        currency=Currency.USD,
        fiscal_year_start_month=1,
        locale="en-US",
        min_cash_reserve=min_cash_reserve,
        target_operating_margin=target_operating_margin,
        max_unsold_inventory_exposure_pct=max_unsold_inventory_exposure_pct,
        created_at=now,
        updated_at=now,
    )


def _scenario(
    *,
    closing_cash: str = "1000.00",
    minimum_projected_cash: str = "1000.00",
    operating_profit: str = "200.00",
    operating_margin: str | None = "0.20",
    revenue: str = "1000.00",
    contribution_margin: str | None = "300.00",
    material_shortage: str | None = "0.00",
    feasible_production: str | None = "100",
    units_produced: str | None = "100",
    unsold_inventory_value: str | None = "100.00",
    invariants_ok: bool = True,
    warnings: list[str] | None = None,
) -> ScenarioResult:
    return ScenarioResult(
        engine_version="0.1.0",
        calculation_timestamp=datetime(2026, 1, 1, 0, 0, 0),
        currency=Currency.USD,
        revenue=revenue,
        direct_costs="500.00",
        gross_profit="500.00",
        gross_margin="0.5000",
        operating_expenses="300.00",
        operating_profit=operating_profit,
        operating_margin=operating_margin,
        cash_inflows="1000.00",
        cash_outflows="500.00",
        net_cash_movement="500.00",
        opening_cash="500.00",
        closing_cash=closing_cash,
        minimum_projected_cash=minimum_projected_cash,
        cash_runway_months="2.00",
        contribution_margin=contribution_margin,
        units_sold="100",
        units_produced=units_produced,
        unsold_inventory_units="10",
        unsold_inventory_value=unsold_inventory_value,
        material_shortage=material_shortage,
        feasible_production=feasible_production,
        warnings=warnings or [],
        invariants_ok=invariants_ok,
        invariants_failures=[],
    )


def test_min_cash_reserve_breach_is_hard() -> None:
    business = _business(min_cash_reserve="5000")
    result = _scenario(closing_cash="2000.00")
    evals = evaluate_rules(result, business)
    rule = next(e for e in evals if e.rule_id == "MIN_CASH_RESERVE")
    assert rule.status == RuleStatus.BREACHED
    assert rule.severity == RuleSeverity.HARD


def test_min_cash_reserve_passed() -> None:
    business = _business(min_cash_reserve="500")
    result = _scenario(closing_cash="1000.00")
    rule = next(e for e in evaluate_rules(result, business) if e.rule_id == "MIN_CASH_RESERVE")
    assert rule.status == RuleStatus.PASSED


def test_min_cash_reserve_not_evaluable_when_unset() -> None:
    business = _business(min_cash_reserve="0")
    result = _scenario(closing_cash="1000.00")
    rule = next(e for e in evaluate_rules(result, business) if e.rule_id == "MIN_CASH_RESERVE")
    assert rule.status == RuleStatus.NOT_EVALUABLE


def test_negative_closing_cash_breach() -> None:
    business = _business()
    result = _scenario(closing_cash="-100.00")
    rule = next(e for e in evaluate_rules(result, business) if e.rule_id == "NEGATIVE_CLOSING_CASH")
    assert rule.status == RuleStatus.BREACHED


def test_min_profit_margin_warning_when_below_target() -> None:
    business = _business(target_operating_margin="0.30")
    result = _scenario(operating_margin="0.20")
    rule = next(e for e in evaluate_rules(result, business) if e.rule_id == "MIN_PROFIT_MARGIN")
    assert rule.status == RuleStatus.WARNING
    assert rule.severity == RuleSeverity.SOFT


def test_min_profit_margin_not_evaluable_when_revenue_zero() -> None:
    business = _business(target_operating_margin="0.10")
    result = _scenario(operating_margin=None)
    rule = next(e for e in evaluate_rules(result, business) if e.rule_id == "MIN_PROFIT_MARGIN")
    assert rule.status == RuleStatus.NOT_EVALUABLE


def test_capacity_exceeded_when_warning_present() -> None:
    business = _business()
    result = _scenario(warnings=["Capacity exceeded: 5 units of production requested beyond capacity."])
    rule = next(e for e in evaluate_rules(result, business) if e.rule_id == "CAPACITY_EXCEEDED")
    assert rule.status == RuleStatus.BREACHED
    assert rule.severity == RuleSeverity.HARD


def test_material_shortage_breach_is_hard() -> None:
    business = _business()
    result = _scenario(material_shortage="50")
    rule = next(e for e in evaluate_rules(result, business) if e.rule_id == "MATERIAL_SHORTAGE")
    assert rule.status == RuleStatus.BREACHED
    assert rule.severity == RuleSeverity.HARD


def test_unsold_inventory_exposure_warning() -> None:
    # revenue=1000, unsold=500 → ratio 0.5 > threshold 0.20
    business = _business(max_unsold_inventory_exposure_pct="0.20")
    result = _scenario(revenue="1000.00", unsold_inventory_value="500.00")
    rule = next(e for e in evaluate_rules(result, business) if e.rule_id == "UNSOLD_INVENTORY_EXPOSURE")
    assert rule.status == RuleStatus.WARNING
    assert rule.severity == RuleSeverity.SOFT


def test_unsold_inventory_exposure_passed_when_within_threshold() -> None:
    # ratio 0.10 < 0.20
    business = _business(max_unsold_inventory_exposure_pct="0.20")
    result = _scenario(revenue="1000.00", unsold_inventory_value="100.00")
    rule = next(e for e in evaluate_rules(result, business) if e.rule_id == "UNSOLD_INVENTORY_EXPOSURE")
    assert rule.status == RuleStatus.PASSED


def test_aggregate_reject_when_any_hard_breach() -> None:
    business = _business()
    result = _scenario(closing_cash="-100.00")
    evals = evaluate_rules(result, business)
    assert aggregate_status(evals) == OverallStatus.REJECT


def test_aggregate_proceed_when_all_passed() -> None:
    business = _business(min_cash_reserve="500", target_operating_margin="0.10")
    result = _scenario(closing_cash="1000.00", operating_margin="0.20", material_shortage="0.00")
    evals = evaluate_rules(result, business)
    assert aggregate_status(evals) == OverallStatus.PROCEED


def test_aggregate_proceed_with_caution_on_soft_warning() -> None:
    business = _business(target_operating_margin="0.30")
    result = _scenario(closing_cash="1000.00", operating_margin="0.20")
    evals = evaluate_rules(result, business)
    assert aggregate_status(evals) == OverallStatus.PROCEED_WITH_CAUTION


def test_aggregate_insufficient_data_when_all_not_evaluable() -> None:
    business = _business(min_cash_reserve="0", target_operating_margin="0")
    # Make material_shortage and unsold_inventory_value None so manufacturing rules are n/a,
    # plus zero operating margin so the margin rule is also n/a.
    result = _scenario(
        operating_margin=None,
        material_shortage=None,
        unsold_inventory_value=None,
        revenue="0.00",
    )
    evals = evaluate_rules(result, business)
    # After enough NOT_EVALUABLE, the result must be INSUFFICIENT_DATA, not PROCEED.
    assert aggregate_status(evals) == OverallStatus.INSUFFICIENT_DATA


def test_hard_breach_dominates_soft_warning() -> None:
    # The whole point of precedence: a hard breach can never be downgraded.
    business = _business(min_cash_reserve="5000", target_operating_margin="0.50")
    result = _scenario(closing_cash="100.00", operating_margin="0.20")
    evals = evaluate_rules(result, business)
    # Both MIN_CASH_RESERVE (breached, hard) and MIN_PROFIT_MARGIN (warning, soft) are present.
    status = aggregate_status(evals)
    assert status == OverallStatus.REJECT


def test_evaluate_returns_every_registered_rule() -> None:
    from app.services.rules.engine import RULES

    business = _business()
    result = _scenario()
    evals = evaluate_rules(result, business)
    assert len(evals) == len(RULES)
