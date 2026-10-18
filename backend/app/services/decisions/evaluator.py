"""Decision evaluator.

Combines:
- A :class:`ScenarioResult` (authoritative)
- A list of :class:`RuleEvaluation` (hard rules are authoritative)
- A list of :class:`LayaAssessment` (advisory)

into a :class:`DecisionReport`. Hard rule ``breached`` always wins; Laya
cannot override a hard rule. The aggregator never collapses a breach
into a soft verdict even if Laya is enthusiastic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.business import BusinessRead
from app.schemas.decision import (
    DecisionReportCreate,
    DecisionReportRead,
    LayaAssessment,
    OverallStatus,
    RuleEvaluation,
    RuleStatus,
)
from app.schemas.finance import ScenarioResult
from app.services.laya.adapter import assess_scenario
from app.services.rules.engine import aggregate_status, evaluate_rules


def _format_assumptions(scenario_inputs: dict[str, Any]) -> list[str]:
    """User-facing list of assumption strings, derived from the typed inputs."""
    notes: list[str] = []
    for k, v in sorted(scenario_inputs.items()):
        if v in (None, "", "0", "0.0"):
            continue
        notes.append(f"{k} = {v}")
    return notes


def _extract_binding_constraints(evaluations: list[RuleEvaluation]) -> list[str]:
    return [
        e.explanation
        for e in evaluations
        if e.severity.value == "hard" and e.status == RuleStatus.BREACHED
    ]


def _extract_key_risks(evaluations: list[RuleEvaluation]) -> list[str]:
    return [
        e.explanation
        for e in evaluations
        if e.severity.value == "soft" and e.status == RuleStatus.WARNING
    ]


def _build_recommendation(
    status: OverallStatus,
    binding: list[str],
    risks: list[str],
    laya: list[LayaAssessment],
) -> str:
    if status == OverallStatus.REJECT:
        return (
            "Hard constraint breach — the scenario cannot proceed as written. "
            f"Address the binding constraints first: {'; '.join(binding) or 'see rule evaluations'}."
        )
    if status == OverallStatus.INSUFFICIENT_DATA:
        return (
            "Insufficient data to make a reliable recommendation. "
            "Provide the missing inputs and re-run the scenario."
        )
    if status == OverallStatus.REVISE:
        return "Revise the scenario to address rule violations before proceeding."
    if status == OverallStatus.PROCEED_WITH_CAUTION:
        base = "Proceed with caution. The scenario is feasible but has risks."
        if risks:
            base += f" Key risks: {'; '.join(risks)}."
        if laya:
            base += f" Laya notes: {', '.join(a.answer_label for a in laya if a.status == 'ok')}."
        return base
    base = "Scenario is feasible and rules pass."
    if laya:
        base += f" Laya notes: {', '.join(a.answer_label for a in laya if a.status == 'ok')}."
    return base


def evaluate(
    payload: DecisionReportCreate,
    scenario_inputs: dict[str, Any],
    scenario_result: ScenarioResult,
    business: BusinessRead,
) -> DecisionReportRead:
    """Evaluate a scenario end-to-end and return a :class:`DecisionReportRead`."""
    rule_evaluations = evaluate_rules(scenario_result, business)
    status = aggregate_status(rule_evaluations)

    # Result dict for Laya — strip Decimal, keep strings.
    result_dict = scenario_result.model_dump()
    rule_dicts = [e.model_dump() for e in rule_evaluations]
    laya = assess_scenario(result_dict, rule_dicts, payload.context.get("business_goal"))

    # Hard constraint precedence: a hard breach cannot be overridden.
    # We do NOT change ``status`` based on Laya — it's already hardcoded.
    binding = _extract_binding_constraints(rule_evaluations)
    risks = _extract_key_risks(rule_evaluations)
    assumptions = _format_assumptions(scenario_inputs)
    missing = [w for w in scenario_result.warnings]

    recommendation = _build_recommendation(status, binding, risks, laya)

    laya_status = "ok" if laya and laya[0].status == "ok" else "unavailable"

    return DecisionReportRead(
        id="",  # filled by the API layer after persistence
        business_id=payload.business_id,
        scenario_version_id=payload.scenario_version_id,
        question=payload.question,
        overall_status=status,
        laya_status=laya_status,
        rule_evaluations=rule_evaluations,
        laya_assessments=laya,
        binding_constraints=binding,
        key_risks=risks,
        recommendation=recommendation,
        missing_information=missing,
        assumptions=assumptions,
        caveats=[
            "Deterministic scenario analysis is not a forecast. Sensitivity is one-at-a-time and bounded.",
            "Laya assessment is advisory and cannot override hard business constraints.",
            "Engineer: MoneyPlant financial engine; LLM and Laya layers are advisory only.",
        ],
        business_goal=payload.context.get("business_goal"),
        calculation_timestamp=scenario_result.calculation_timestamp or datetime.now(timezone.utc),
    )


__all__ = ["evaluate"]