"""Rule engine: deterministic, explainable, configurable.

The engine has a small registry of rule functions. Each rule takes a
:class:`ScenarioResult` and a business's :class:`BusinessRead` and returns
a :class:`RuleEvaluation`. Aggregation precedence: a single ``breached``
hard rule forces overall status to ``reject``; soft ``warning`` rules
downgrade ``proceed`` to ``proceed_with_caution``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from app.schemas.business import BusinessRead
from app.schemas.decision import (
    OverallStatus,
    RuleEvaluation,
    RuleSeverity,
    RuleStatus,
)
from app.schemas.finance import ScenarioResult

RULE_VERSION = "0.1.0"


def _to_decimal(value: str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(value)


def _null_safe_str(value: str | None) -> str:
    return value if value is not None else "—"


def _rule_min_cash_reserve(result: ScenarioResult, business: BusinessRead) -> RuleEvaluation:
    threshold = _to_decimal(business.min_cash_reserve)
    actual = _to_decimal(result.closing_cash)
    if threshold <= 0:
        return RuleEvaluation(
            rule_id="MIN_CASH_RESERVE",
            rule_version=RULE_VERSION,
            name="Minimum cash reserve",
            severity=RuleSeverity.INFO,
            status=RuleStatus.NOT_EVALUABLE,
            actual_value=result.closing_cash,
            threshold=str(threshold),
            unit="currency",
            explanation="No minimum cash reserve configured. Set one in business settings to enable this rule.",
            related_metric="closing_cash",
            evidence={"closing_cash": result.closing_cash},
        )
    if actual < threshold:
        return RuleEvaluation(
            rule_id="MIN_CASH_RESERVE",
            rule_version=RULE_VERSION,
            name="Minimum cash reserve",
            severity=RuleSeverity.HARD,
            status=RuleStatus.BREACHED,
            actual_value=result.closing_cash,
            threshold=str(threshold),
            unit="currency",
            explanation=(
                f"Projected closing cash ({_null_safe_str(result.closing_cash)}) is below the "
                f"configured minimum cash reserve ({threshold})."
            ),
            related_metric="closing_cash",
            evidence={"closing_cash": result.closing_cash, "min_cash_reserve": str(threshold)},
            corrective_action="Reduce planned expenses, delay non-essential purchases, or shorten payment terms.",
        )
    return RuleEvaluation(
        rule_id="MIN_CASH_RESERVE",
        rule_version=RULE_VERSION,
        name="Minimum cash reserve",
        severity=RuleSeverity.HARD,
        status=RuleStatus.PASSED,
        actual_value=result.closing_cash,
        threshold=str(threshold),
        unit="currency",
        explanation="Projected closing cash meets the minimum reserve.",
        related_metric="closing_cash",
        evidence={"closing_cash": result.closing_cash, "min_cash_reserve": str(threshold)},
    )


def _rule_negative_closing_cash(result: ScenarioResult, _business: BusinessRead) -> RuleEvaluation:
    actual = _to_decimal(result.closing_cash)
    if actual < 0:
        return RuleEvaluation(
            rule_id="NEGATIVE_CLOSING_CASH",
            rule_version=RULE_VERSION,
            name="Negative closing cash",
            severity=RuleSeverity.HARD,
            status=RuleStatus.BREACHED,
            actual_value=result.closing_cash,
            threshold="0",
            unit="currency",
            explanation=f"Projected closing cash is negative ({_null_safe_str(result.closing_cash)}).",
            related_metric="closing_cash",
            evidence={"closing_cash": result.closing_cash, "min_projected_cash": result.minimum_projected_cash},
            corrective_action="Reduce planned outflows, accelerate collections, or arrange a credit line.",
        )
    return RuleEvaluation(
        rule_id="NEGATIVE_CLOSING_CASH",
        rule_version=RULE_VERSION,
        name="Negative closing cash",
        severity=RuleSeverity.HARD,
        status=RuleStatus.PASSED,
        actual_value=result.closing_cash,
        threshold="0",
        unit="currency",
        explanation="Projected closing cash is non-negative.",
        related_metric="closing_cash",
        evidence={"closing_cash": result.closing_cash},
    )


def _rule_min_profit_margin(result: ScenarioResult, business: BusinessRead) -> RuleEvaluation:
    target = _to_decimal(business.target_operating_margin)
    actual = _to_decimal(result.operating_margin) if result.operating_margin else None
    if target <= 0:
        return RuleEvaluation(
            rule_id="MIN_PROFIT_MARGIN",
            rule_version=RULE_VERSION,
            name="Target operating margin",
            severity=RuleSeverity.INFO,
            status=RuleStatus.NOT_EVALUABLE,
            actual_value=result.operating_margin,
            threshold=str(target),
            unit="ratio",
            explanation="No target operating margin configured. Set one in business settings to enable this rule.",
            related_metric="operating_margin",
            evidence={"operating_margin": result.operating_margin},
        )
    if actual is None:
        return RuleEvaluation(
            rule_id="MIN_PROFIT_MARGIN",
            rule_version=RULE_VERSION,
            name="Target operating margin",
            severity=RuleSeverity.SOFT,
            status=RuleStatus.NOT_EVALUABLE,
            actual_value=None,
            threshold=str(target),
            unit="ratio",
            explanation="Cannot evaluate margin: revenue is zero.",
            related_metric="operating_margin",
            evidence={"revenue": result.revenue, "operating_margin": None},
        )
    if actual < target:
        return RuleEvaluation(
            rule_id="MIN_PROFIT_MARGIN",
            rule_version=RULE_VERSION,
            name="Target operating margin",
            severity=RuleSeverity.SOFT,
            status=RuleStatus.WARNING,
            actual_value=str(actual),
            threshold=str(target),
            unit="ratio",
            explanation=f"Operating margin ({actual:.4f}) is below the target ({target:.4f}).",
            related_metric="operating_margin",
            evidence={"operating_margin": result.operating_margin, "target": str(target)},
            corrective_action="Review pricing, direct costs, or operating expenses.",
        )
    return RuleEvaluation(
        rule_id="MIN_PROFIT_MARGIN",
        rule_version=RULE_VERSION,
        name="Target operating margin",
        severity=RuleSeverity.SOFT,
        status=RuleStatus.PASSED,
        actual_value=str(actual),
        threshold=str(target),
        unit="ratio",
        explanation="Operating margin meets the target.",
        related_metric="operating_margin",
        evidence={"operating_margin": result.operating_margin, "target": str(target)},
    )


def _rule_negative_contribution_margin(result: ScenarioResult, _business: BusinessRead) -> RuleEvaluation:
    if result.contribution_margin is None:
        return RuleEvaluation(
            rule_id="NEGATIVE_CONTRIBUTION_MARGIN",
            rule_version=RULE_VERSION,
            name="Negative contribution margin",
            severity=RuleSeverity.SOFT,
            status=RuleStatus.NOT_EVALUABLE,
            actual_value=None,
            threshold="0",
            unit="currency",
            explanation="Contribution margin is not applicable for this scenario.",
            related_metric="contribution_margin",
        )
    actual = _to_decimal(result.contribution_margin)
    if actual < 0:
        return RuleEvaluation(
            rule_id="NEGATIVE_CONTRIBUTION_MARGIN",
            rule_version=RULE_VERSION,
            name="Negative contribution margin",
            severity=RuleSeverity.SOFT,
            status=RuleStatus.WARNING,
            actual_value=result.contribution_margin,
            threshold="0",
            unit="currency",
            explanation="Contribution margin is negative — variable costs exceed revenue.",
            related_metric="contribution_margin",
            evidence={"contribution_margin": result.contribution_margin},
            corrective_action="Raise price, reduce direct cost per unit, or reduce variable overhead.",
        )
    return RuleEvaluation(
        rule_id="NEGATIVE_CONTRIBUTION_MARGIN",
        rule_version=RULE_VERSION,
        name="Negative contribution margin",
        severity=RuleSeverity.SOFT,
        status=RuleStatus.PASSED,
        actual_value=result.contribution_margin,
        threshold="0",
        unit="currency",
        explanation="Contribution margin is non-negative.",
        related_metric="contribution_margin",
        evidence={"contribution_margin": result.contribution_margin},
    )


def _rule_material_shortage(result: ScenarioResult, _business: BusinessRead) -> RuleEvaluation:
    if result.material_shortage is None:
        return RuleEvaluation(
            rule_id="MATERIAL_SHORTAGE",
            rule_version=RULE_VERSION,
            name="Material shortage",
            severity=RuleSeverity.INFO,
            status=RuleStatus.NOT_EVALUABLE,
            actual_value=None,
            threshold="0",
            unit="units",
            explanation="Material shortage is not applicable for this industry.",
            related_metric="material_shortage",
        )
    actual = _to_decimal(result.material_shortage)
    if actual > 0:
        return RuleEvaluation(
            rule_id="MATERIAL_SHORTAGE",
            rule_version=RULE_VERSION,
            name="Material shortage",
            severity=RuleSeverity.HARD,
            status=RuleStatus.BREACHED,
            actual_value=result.material_shortage,
            threshold="0",
            unit="units",
            explanation="Planned production exceeds the available raw material.",
            related_metric="material_shortage",
            evidence={"material_shortage": result.material_shortage},
            corrective_action="Increase raw-material purchase, reduce planned production, or relax waste assumption.",
        )
    return RuleEvaluation(
        rule_id="MATERIAL_SHORTAGE",
        rule_version=RULE_VERSION,
        name="Material shortage",
        severity=RuleSeverity.HARD,
        status=RuleStatus.PASSED,
        actual_value=result.material_shortage,
        threshold="0",
        unit="units",
        explanation="Available material covers planned production.",
        related_metric="material_shortage",
        evidence={"material_shortage": result.material_shortage},
    )


def _rule_capacity_exceeded(result: ScenarioResult, _business: BusinessRead) -> RuleEvaluation:
    if result.feasible_production is None or result.units_produced is None:
        return RuleEvaluation(
            rule_id="CAPACITY_EXCEEDED",
            rule_version=RULE_VERSION,
            name="Capacity exceeded",
            severity=RuleSeverity.INFO,
            status=RuleStatus.NOT_EVALUABLE,
            actual_value=None,
            threshold=None,
            unit="units",
            explanation="Capacity check is not applicable for this industry.",
            related_metric="capacity",
        )
    # feasible_production is the post-cap value; comparing to inputs is the runner's job.
    # We surface a warning if the scenario mentions capacity in the warnings list.
    if any("capacity" in w.lower() for w in result.warnings):
        return RuleEvaluation(
            rule_id="CAPACITY_EXCEEDED",
            rule_version=RULE_VERSION,
            name="Capacity exceeded",
            severity=RuleSeverity.HARD,
            status=RuleStatus.BREACHED,
            actual_value=result.units_produced,
            threshold=result.feasible_production,
            unit="units",
            explanation="Planned production exceeds the stated production capacity.",
            related_metric="capacity",
            evidence={"warnings": result.warnings},
            corrective_action="Increase capacity (overtime, second shift, outsourcing) or reduce planned production.",
        )
    return RuleEvaluation(
        rule_id="CAPACITY_EXCEEDED",
        rule_version=RULE_VERSION,
        name="Capacity exceeded",
        severity=RuleSeverity.HARD,
        status=RuleStatus.PASSED,
        actual_value=result.units_produced,
        threshold=result.feasible_production,
        unit="units",
        explanation="Planned production is within stated capacity.",
        related_metric="capacity",
    )


def _rule_unsold_inventory_exposure(result: ScenarioResult, business: BusinessRead) -> RuleEvaluation:
    if result.unsold_inventory_value is None or result.revenue is None:
        return RuleEvaluation(
            rule_id="UNSOLD_INVENTORY_EXPOSURE",
            rule_version=RULE_VERSION,
            name="Unsold inventory exposure",
            severity=RuleSeverity.INFO,
            status=RuleStatus.NOT_EVALUABLE,
            actual_value=None,
            threshold=str(business.max_unsold_inventory_exposure_pct),
            unit="ratio",
            explanation="Unsold inventory check is not applicable for this industry.",
            related_metric="unsold_inventory_value",
        )
    unsold = _to_decimal(result.unsold_inventory_value)
    revenue = _to_decimal(result.revenue)
    if revenue <= 0:
        return RuleEvaluation(
            rule_id="UNSOLD_INVENTORY_EXPOSURE",
            rule_version=RULE_VERSION,
            name="Unsold inventory exposure",
            severity=RuleSeverity.SOFT,
            status=RuleStatus.NOT_EVALUABLE,
            actual_value=None,
            threshold=str(business.max_unsold_inventory_exposure_pct),
            unit="ratio",
            explanation="Cannot evaluate exposure: revenue is zero.",
            related_metric="unsold_inventory_value",
        )
    ratio = unsold / revenue
    threshold = _to_decimal(business.max_unsold_inventory_exposure_pct)
    if ratio > threshold:
        return RuleEvaluation(
            rule_id="UNSOLD_INVENTORY_EXPOSURE",
            rule_version=RULE_VERSION,
            name="Unsold inventory exposure",
            severity=RuleSeverity.SOFT,
            status=RuleStatus.WARNING,
            actual_value=f"{ratio:.4f}",
            threshold=str(threshold),
            unit="ratio",
            explanation=f"Unsold-inventory value is {ratio:.2%} of revenue, above the configured maximum.",
            related_metric="unsold_inventory_value",
            evidence={"unsold_inventory_value": result.unsold_inventory_value, "revenue": result.revenue},
            corrective_action="Reduce planned production, increase expected demand, or run a promotion.",
        )
    return RuleEvaluation(
        rule_id="UNSOLD_INVENTORY_EXPOSURE",
        rule_version=RULE_VERSION,
        name="Unsold inventory exposure",
        severity=RuleSeverity.SOFT,
        status=RuleStatus.PASSED,
        actual_value=f"{ratio:.4f}",
        threshold=str(threshold),
        unit="ratio",
        explanation="Unsold-inventory exposure is within the configured maximum.",
        related_metric="unsold_inventory_value",
    )


def _rule_missing_critical_data(result: ScenarioResult, _business: BusinessRead) -> RuleEvaluation:
    if not result.invariants_ok:
        return RuleEvaluation(
            rule_id="MISSING_CRITICAL_DATA",
            rule_version=RULE_VERSION,
            name="Missing or inconsistent critical data",
            severity=RuleSeverity.INFO,
            status=RuleStatus.NOT_EVALUABLE,
            actual_value=None,
            threshold=None,
            unit=None,
            explanation=(
                "Internal invariant checks failed. Treat the result as provisional and re-check inputs."
            ),
            related_metric="invariants",
            evidence={"invariants_failures": result.invariants_failures},
        )
    if result.warnings:
        return RuleEvaluation(
            rule_id="MISSING_CRITICAL_DATA",
            rule_version=RULE_VERSION,
            name="Data warnings present",
            severity=RuleSeverity.INFO,
            status=RuleStatus.WARNING,
            actual_value=None,
            threshold=None,
            unit=None,
            explanation="One or more data warnings are present. See the warnings list.",
            related_metric="warnings",
            evidence={"warnings": result.warnings},
        )
    return RuleEvaluation(
        rule_id="MISSING_CRITICAL_DATA",
        rule_version=RULE_VERSION,
        name="Missing or inconsistent critical data",
        severity=RuleSeverity.INFO,
        status=RuleStatus.PASSED,
        actual_value=None,
        threshold=None,
        unit=None,
        explanation="No missing or inconsistent critical data detected.",
        related_metric="invariants",
    )


# Registry of all rules. Order is for display; the engine evaluates all of them.
RULES: list[tuple[str, Callable[[ScenarioResult, BusinessRead], RuleEvaluation]]] = [
    ("NEGATIVE_CLOSING_CASH", _rule_negative_closing_cash),
    ("MIN_CASH_RESERVE", _rule_min_cash_reserve),
    ("CAPACITY_EXCEEDED", _rule_capacity_exceeded),
    ("MATERIAL_SHORTAGE", _rule_material_shortage),
    ("MIN_PROFIT_MARGIN", _rule_min_profit_margin),
    ("NEGATIVE_CONTRIBUTION_MARGIN", _rule_negative_contribution_margin),
    ("UNSOLD_INVENTORY_EXPOSURE", _rule_unsold_inventory_exposure),
    ("MISSING_CRITICAL_DATA", _rule_missing_critical_data),
]


def evaluate_rules(result: ScenarioResult, business: BusinessRead) -> list[RuleEvaluation]:
    return [fn(result, business) for _id, fn in RULES]


def aggregate_status(evaluations: list[RuleEvaluation]) -> OverallStatus:
    if not evaluations:
        return OverallStatus.INSUFFICIENT_DATA
    # Hard rule breach -> reject, regardless of LLM or other votes.
    if any(
        e.severity == RuleSeverity.HARD and e.status == RuleStatus.BREACHED
        for e in evaluations
    ):
        return OverallStatus.REJECT
    # INSUFFICIENT_DATA when the engine has too little signal — too many rules
    # are not evaluable for the business / scenario combination. Threshold is
    # "more than half": a majority of N/E means we can't responsibly give a
    # verdict either way.
    not_evaluable_count = sum(
        1 for e in evaluations if e.status == RuleStatus.NOT_EVALUABLE
    )
    if not_evaluable_count >= len(evaluations) / 2:
        return OverallStatus.INSUFFICIENT_DATA
    # Any soft warning -> proceed_with_caution
    if any(e.status == RuleStatus.WARNING for e in evaluations):
        return OverallStatus.PROCEED_WITH_CAUTION
    if all(e.status in (RuleStatus.PASSED, RuleStatus.NOT_EVALUABLE) for e in evaluations):
        return OverallStatus.PROCEED
    return OverallStatus.REVISE


__all__ = [
    "RULE_VERSION",
    "RULES",
    "evaluate_rules",
    "aggregate_status",
]