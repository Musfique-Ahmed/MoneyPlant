"""Decision endpoints — evaluate, retrieve, explain.

Hard rules always win. Laya is advisory. The LLM explanation is a
separate request that doesn't change the underlying decision.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.business import Business
from app.models.decision import DecisionReport, LlmExplanation
from app.models.scenario import ScenarioVersion
from app.schemas.business import BusinessRead, Industry
from app.schemas.decision import (
    DecisionExplainRequest,
    DecisionReportCreate,
    DecisionReportRead,
)
from app.schemas.finance import parse_inputs_dict
from app.schemas.llm import Explanation, ExplanationContext
from app.schemas.money import Currency
from app.services.decisions.evaluator import evaluate
from app.services.llm.factory import get_provider
from app.services.simulation.runner import run_scenario

router = APIRouter(prefix="/decisions", tags=["decisions"])


# --- helpers --------------------------------------------------------------


def _business_to_read(b: Business) -> BusinessRead:
    return BusinessRead(
        id=b.id,
        name=b.name,
        industry=Industry(b.industry),
        currency=Currency(b.currency),
        fiscal_year_start_month=b.fiscal_year_start_month,
        locale=b.locale,
        min_cash_reserve=str(b.min_cash_reserve),
        target_operating_margin=str(b.target_operating_margin),
        max_unsold_inventory_exposure_pct=str(b.max_unsold_inventory_exposure_pct),
        created_at=b.created_at,
        updated_at=b.updated_at,
    )


def _report_to_dict(d: DecisionReport) -> dict[str, Any]:
    try:
        return json.loads(d.report_json)
    except json.JSONDecodeError:
        return {}


def _read_to_db(d: DecisionReport) -> DecisionReportRead:
    payload = _report_to_dict(d)
    payload["id"] = d.id
    payload["business_id"] = d.business_id
    payload["scenario_version_id"] = d.scenario_version_id
    try:
        return DecisionReportRead.model_validate(payload)
    except Exception:  # noqa: BLE001
        # Defensive: legacy/unparseable reports become "insufficient_data".
        return DecisionReportRead(
            id=d.id,
            business_id=d.business_id,
            scenario_version_id=d.scenario_version_id,
            question=d.question,
            overall_status="insufficient_data",
            laya_status="not_used",
            rule_evaluations=[],
            laya_assessments=[],
            binding_constraints=[],
            key_risks=[],
            recommendation="This decision report could not be parsed.",
            missing_information=["Corrupt report payload."],
            assumptions=[],
            caveats=[],
            business_goal=None,
            calculation_timestamp=d.created_at,
        )


# --- routes ---------------------------------------------------------------


@router.post("/evaluate", response_model=DecisionReportRead, status_code=201)
def evaluate_decision(
    payload: DecisionReportCreate, db: Session = Depends(get_db)
) -> DecisionReportRead:
    """Run the rule engine (+ Laya) against a scenario, persist the report."""
    business = db.get(Business, payload.business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="business_not_found")
    biz = _business_to_read(business)

    # If a scenario_version_id is provided, load its inputs; otherwise
    # require ``context.inputs`` in the payload.
    if payload.scenario_version_id:
        v = db.get(ScenarioVersion, payload.scenario_version_id)
        if v is None:
            raise HTTPException(status_code=404, detail="scenario_version_not_found")
        try:
            inputs = json.loads(v.inputs_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"corrupt_scenario_inputs: {exc}") from exc
    else:
        inputs = payload.context.get("inputs") if isinstance(payload.context, dict) else None
        if not inputs or not isinstance(inputs, dict):
            raise HTTPException(status_code=400, detail="inputs_required (no scenario_version_id)")

    try:
        parse_inputs_dict(inputs)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid_inputs: {exc}") from exc

    result = run_scenario(inputs, business.currency)
    report = evaluate(payload, inputs, result, biz)
    d = DecisionReport(
        business_id=business.id,
        scenario_version_id=payload.scenario_version_id,
        question=payload.question,
        report_json=report.model_dump_json(),
        overall_status=report.overall_status.value,
        laya_status=report.laya_status,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return _read_to_db(d)


@router.get("", response_model=list[DecisionReportRead])
def list_decisions(
    business_id: str = Query(...), db: Session = Depends(get_db)
) -> list[DecisionReportRead]:
    rows = (
        db.query(DecisionReport)
        .filter(DecisionReport.business_id == business_id)
        .order_by(DecisionReport.created_at.desc())
        .all()
    )
    return [_read_to_db(d) for d in rows]


@router.get("/{report_id}", response_model=DecisionReportRead)
def get_decision(report_id: str, db: Session = Depends(get_db)) -> DecisionReportRead:
    d = db.get(DecisionReport, report_id)
    if d is None:
        raise HTTPException(status_code=404, detail="decision_not_found")
    return _read_to_db(d)


@router.post("/{report_id}/explain", response_model=Explanation)
def explain_decision(
    report_id: str,
    payload: DecisionExplainRequest = DecisionExplainRequest(),
    db: Session = Depends(get_db),
) -> Explanation:
    """Run the configured LLM provider against the decision report.

    Does NOT modify the report. The LLM output is stored in
    ``llm_explanations`` for audit and review.
    """
    d = db.get(DecisionReport, report_id)
    if d is None:
        raise HTTPException(status_code=404, detail="decision_not_found")
    business = db.get(Business, d.business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="business_not_found")
    biz = _business_to_read(business)

    payload_dict = _report_to_dict(d)
    # Minimal structured context — no raw transactions.
    baseline: dict[str, Any] = {}
    scenarios: list[dict[str, Any]] = []
    if d.scenario_version_id:
        v = db.get(ScenarioVersion, d.scenario_version_id)
        if v is not None:
            try:
                scenarios.append(
                    {
                        "inputs": json.loads(v.inputs_json),
                        "result": json.loads(v.result_json or "{}"),
                    }
                )
            except json.JSONDecodeError:
                pass
    rule_dicts = payload_dict.get("rule_evaluations", [])
    laya_dicts = payload_dict.get("laya_assessments", [])

    provider = get_provider(payload.provider_mode)
    explanation = provider.explain(
        ExplanationContext.model_validate(
            {
                "business_industry": biz.industry.value,
                "reporting_period": "scenario",
                "user_question": d.question,
                "computed_baseline": baseline,
                "computed_scenarios": scenarios,
                "rule_evaluations": rule_dicts,
                "laya_assessment": {"assessments": laya_dicts},
                "assumptions": payload_dict.get("assumptions", []),
                "missing_information": payload_dict.get("missing_information", []),
                "business_goal": payload_dict.get("business_goal"),
            }
        )
    )

    db.add(
        LlmExplanation(
            decision_report_id=d.id,
            provider=explanation.provider,
            model=explanation.model,
            mode=explanation.mode.value,
            status=explanation.status,
            content_json=explanation.model_dump_json(),
        )
    )
    db.commit()
    return explanation


__all__ = ["router"]
