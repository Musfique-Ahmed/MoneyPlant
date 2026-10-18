"""Scenario endpoints — simulate, save, list, retrieve, rerun, compare."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.business import Business
from app.models.scenario import Scenario, ScenarioVersion
from app.schemas.business import BusinessRead, Industry
from app.schemas.finance import (
    ScenarioComparison,
    ScenarioComparisonRow,
    ScenarioCreate,
    ScenarioRead,
    ScenarioResult,
    SensitivityAxis,
    SensitivityRequest,
    SensitivityResponse,
    SimulateRequest,
    SimulateResponse,
    parse_inputs_dict,
)
from app.schemas.money import Currency
from app.services.simulation.runner import run_scenario
from app.services.simulation.sensitivity import DEFAULT_MULTIPLIERS, run_sensitivity

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


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


def _result_from_json(payload: str | None) -> ScenarioResult | None:
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    try:
        return ScenarioResult.model_validate(data)
    except Exception:  # noqa: BLE001
        return None


def _scenario_to_read(s: Scenario, db: Session) -> ScenarioRead:
    latest = (
        db.query(ScenarioVersion)
        .filter(ScenarioVersion.scenario_id == s.id)
        .order_by(ScenarioVersion.version_number.desc())
        .first()
    )
    return ScenarioRead(
        id=s.id,
        business_id=s.business_id,
        name=s.name,
        industry=Industry(s.industry),
        description=s.description,
        status=s.status,
        created_at=s.created_at,
        updated_at=s.updated_at,
        latest_version_number=latest.version_number if latest else None,
        latest_version_id=latest.id if latest else None,
        latest_result=_result_from_json(latest.result_json) if latest else None,
    )


# --- routes ---------------------------------------------------------------


@router.post("/simulate", response_model=SimulateResponse)
def simulate(payload: SimulateRequest, db: Session = Depends(get_db)) -> SimulateResponse:
    """Run a scenario in memory (no DB write). Returns the result + optional sensitivity."""
    business = db.get(Business, payload.business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="business_not_found")
    try:
        inputs = parse_inputs_dict(payload.inputs)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid_inputs: {exc}") from exc
    result = run_scenario(payload.inputs, business.currency)
    return SimulateResponse(result=result, sensitivity=None)


@router.post("/simulate/sensitivity", response_model=SensitivityResponse)
def simulate_sensitivity(payload: SensitivityRequest, db: Session = Depends(get_db)) -> SensitivityResponse:
    business = db.get(Business, payload.business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="business_not_found")
    try:
        parse_inputs_dict(payload.inputs)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid_inputs: {exc}") from exc
    axes = payload.axes or list(SensitivityAxis)
    multipliers = [Decimal(m) for m in (payload.multipliers or list(DEFAULT_MULTIPLIERS))]
    return run_sensitivity(
        business_id=payload.business_id,
        inputs=payload.inputs,
        currency=business.currency,
        axes=axes,
        multipliers=multipliers,
    )


@router.post("", response_model=ScenarioRead, status_code=201)
def create_scenario(payload: ScenarioCreate, db: Session = Depends(get_db)) -> ScenarioRead:
    business = db.get(Business, payload.business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="business_not_found")
    try:
        inputs = parse_inputs_dict(payload.inputs)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid_inputs: {exc}") from exc
    industry = inputs.industry
    if industry.value != business.industry:
        raise HTTPException(
            status_code=400,
            detail=f"scenario_industry_mismatch: {industry.value} != {business.industry}",
        )
    s = Scenario(
        business_id=business.id,
        name=payload.name,
        industry=industry.value,
        description=payload.description or "",
        status="draft",
    )
    db.add(s)
    db.flush()
    result = run_scenario(payload.inputs, business.currency)
    v = ScenarioVersion(
        scenario_id=s.id,
        version_number=1,
        inputs_json=json.dumps(payload.inputs),
        result_json=result.model_dump_json(),
        engine_version=result.engine_version,
        calculation_timestamp=datetime.now(timezone.utc),
    )
    db.add(v)
    db.commit()
    db.refresh(s)
    return _scenario_to_read(s, db)


@router.get("", response_model=list[ScenarioRead])
def list_scenarios(
    business_id: str = Query(...), db: Session = Depends(get_db)
) -> list[ScenarioRead]:
    rows = (
        db.query(Scenario)
        .filter(Scenario.business_id == business_id)
        .order_by(Scenario.created_at.desc())
        .all()
    )
    return [_scenario_to_read(s, db) for s in rows]


@router.get("/{scenario_id}", response_model=ScenarioRead)
def get_scenario(scenario_id: str, db: Session = Depends(get_db)) -> ScenarioRead:
    s = db.get(Scenario, scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail="scenario_not_found")
    return _scenario_to_read(s, db)


@router.get("/{scenario_id}/versions", response_model=list[ScenarioResult])
def list_versions(scenario_id: str, db: Session = Depends(get_db)) -> list[ScenarioResult]:
    s = db.get(Scenario, scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail="scenario_not_found")
    rows = (
        db.query(ScenarioVersion)
        .filter(ScenarioVersion.scenario_id == scenario_id)
        .order_by(ScenarioVersion.version_number.asc())
        .all()
    )
    out: list[ScenarioResult] = []
    for r in rows:
        r2 = _result_from_json(r.result_json)
        if r2 is not None:
            out.append(r2)
    return out


@router.post("/{scenario_id}/rerun", response_model=ScenarioRead)
def rerun_scenario(scenario_id: str, db: Session = Depends(get_db)) -> ScenarioRead:
    s = db.get(Scenario, scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail="scenario_not_found")
    business = db.get(Business, s.business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="business_not_found")
    latest = (
        db.query(ScenarioVersion)
        .filter(ScenarioVersion.scenario_id == scenario_id)
        .order_by(ScenarioVersion.version_number.desc())
        .first()
    )
    if latest is None:
        raise HTTPException(status_code=400, detail="scenario_has_no_versions")
    try:
        inputs = json.loads(latest.inputs_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"corrupt_scenario_inputs: {exc}") from exc
    new_version = (latest.version_number or 0) + 1
    result = run_scenario(inputs, business.currency)
    v = ScenarioVersion(
        scenario_id=s.id,
        version_number=new_version,
        inputs_json=latest.inputs_json,
        result_json=result.model_dump_json(),
        engine_version=result.engine_version,
        calculation_timestamp=datetime.now(timezone.utc),
    )
    db.add(v)
    db.commit()
    db.refresh(s)
    return _scenario_to_read(s, db)


@router.post("/compare", response_model=ScenarioComparison)
def compare_scenarios(payload: dict[str, Any], db: Session = Depends(get_db)) -> ScenarioComparison:
    """Compare 1-5 scenarios side-by-side. Baseline = first id in the list."""
    business_id = payload.get("business_id")
    scenario_ids = payload.get("scenario_ids") or []
    if not business_id or not isinstance(business_id, str):
        raise HTTPException(status_code=400, detail="business_id_required")
    if not (1 <= len(scenario_ids) <= 5):
        raise HTTPException(status_code=400, detail="scenario_ids must be 1-5")
    business = db.get(Business, business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="business_not_found")

    rows_out: list[ScenarioComparisonRow] = []
    for sid in scenario_ids:
        s = db.get(Scenario, sid)
        if s is None or s.business_id != business_id:
            raise HTTPException(status_code=404, detail=f"scenario_not_found: {sid}")
        latest = (
            db.query(ScenarioVersion)
            .filter(ScenarioVersion.scenario_id == sid)
            .order_by(ScenarioVersion.version_number.desc())
            .first()
        )
        if latest is None:
            raise HTTPException(status_code=400, detail=f"scenario_has_no_versions: {sid}")
        r = _result_from_json(latest.result_json)
        if r is None:
            raise HTTPException(status_code=500, detail=f"scenario_result_unparseable: {sid}")
        rows_out.append(
            ScenarioComparisonRow(
                scenario_id=sid,
                scenario_name=s.name,
                industry=Industry(s.industry),
                revenue=r.revenue,
                direct_costs=r.direct_costs,
                gross_profit=r.gross_profit,
                operating_profit=r.operating_profit,
                operating_margin=r.operating_margin,
                closing_cash=r.closing_cash,
                minimum_projected_cash=r.minimum_projected_cash,
                unsold_inventory_value=r.unsold_inventory_value,
                business_goal=(json.loads(latest.inputs_json).get("business_goal") if latest.inputs_json else None),
            )
        )

    baseline = rows_out[0]
    diffs: list[dict[str, str | None]] = []
    for row in rows_out[1:]:
        diffs.append(_diff_row(baseline, row))

    return ScenarioComparison(
        rows=rows_out,
        baseline_id=baseline.scenario_id,
        diffs=diffs,
        warnings=[],
    )


def _diff_row(b: ScenarioComparisonRow, r: ScenarioComparisonRow) -> dict[str, str | None]:
    def pct(base: str, other: str) -> str | None:
        try:
            b_d, o_d = Decimal(base), Decimal(other)
        except Exception:  # noqa: BLE001
            return None
        if b_d == 0:
            return None
        return str(((o_d - b_d) / b_d).quantize(Decimal("0.0001")))

    def diff(base: str, other: str) -> str | None:
        try:
            return str(Decimal(other) - Decimal(base))
        except Exception:  # noqa: BLE001
            return None

    return {
        "scenario_id": r.scenario_id,
        "revenue_delta": diff(b.revenue, r.revenue),
        "revenue_delta_pct": pct(b.revenue, r.revenue),
        "operating_profit_delta": diff(b.operating_profit, r.operating_profit),
        "operating_profit_delta_pct": pct(b.operating_profit, r.operating_profit),
        "closing_cash_delta": diff(b.closing_cash, r.closing_cash),
        "closing_cash_delta_pct": pct(b.closing_cash, r.closing_cash),
    }


__all__ = ["router"]
