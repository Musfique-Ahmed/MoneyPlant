"""Seed demo data: one business per industry (5 total) + sample data imports.

Run from the project root with the backend on PYTHONPATH:

    cd backend && python -m scripts.seed_demo

Or directly:

    cd backend && PYTHONPATH=. python ../scripts/seed_demo.py

The script is idempotent: if a business with the same name + industry
exists, it's skipped. The sample CSVs live in ``sample_data/`` and are
loaded via the same ingestion code the API uses.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

# Make the backend importable when run as a script.
BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from typing import Any  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.business import Business  # noqa: E402
from app.models.import_job import ImportJob  # noqa: E402
from app.models.scenario import Scenario, ScenarioVersion  # noqa: E402
from app.models.transaction import Transaction  # noqa: E402
from app.schemas.business import Industry  # noqa: E402
from app.services.ingestion.csv import parse_rows, suggest_mapping  # noqa: E402
from app.services.simulation.runner import run_scenario  # noqa: E402

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"

DEMO_BUSINESSES: list[dict[str, Any]] = [
    {
        "name": "Aurora Garments (demo)",
        "industry": Industry.MANUFACTURING.value,
        "currency": "USD",
        "min_cash_reserve": "5000",
        "target_operating_margin": "0.15",
        "max_unsold_inventory_exposure_pct": "0.20",
        "csv": "clothing_demo.csv",
        "scenario_name": "Q1 baseline",
        "scenario_inputs": {
            "industry": "manufacturing",
            "opening_cash": "15000",
            "opening_raw_material_qty": "200",
            "planned_raw_material_purchase_qty": "300",
            "material_unit_cost": "4.50",
            "material_per_unit": "1.5",
            "material_waste_pct": "0.05",
            "planned_production_qty": "300",
            "production_capacity_qty": "320",
            "labor_cost_per_unit": "6.00",
            "other_variable_cost_per_unit": "0.50",
            "operating_expenses": "2500",
            "selling_price": "24.00",
            "expected_units_sold": "280",
            "customer_payment_delay_periods": 1,
            "supplier_payment_delay_periods": 0,
            "horizon_months": 3,
            "business_goal": "Reach 15% operating margin while keeping closing cash above $5,000.",
        },
    },
    {
        "name": "Main Street Boutique (demo)",
        "industry": Industry.RETAIL.value,
        "currency": "USD",
        "min_cash_reserve": "3000",
        "target_operating_margin": "0.10",
        "max_unsold_inventory_exposure_pct": "0.25",
        "csv": "retail_demo.csv",
        "scenario_name": "Q1 baseline",
        "scenario_inputs": {
            "industry": "retail",
            "opening_cash": "8000",
            "opening_inventory_units": "100",
            "planned_purchase_units": "200",
            "purchase_unit_cost": "12.00",
            "selling_price": "29.00",
            "expected_units_sold": "240",
            "shrinkage_pct": "0.02",
            "operating_expenses": "1800",
            "supplier_payment_delay_periods": 0,
            "customer_payment_delay_periods": 0,
            "horizon_months": 2,
            "business_goal": "Hold unsold-inventory exposure under 25% of revenue.",
        },
    },
    {
        "name": "Helios Consulting (demo)",
        "industry": Industry.SERVICE.value,
        "currency": "USD",
        "min_cash_reserve": "4000",
        "target_operating_margin": "0.20",
        "max_unsold_inventory_exposure_pct": "0",
        "csv": "service_demo.csv",
        "scenario_name": "Q1 baseline",
        "scenario_inputs": {
            "industry": "service",
            "opening_cash": "12000",
            "billable_hours_capacity": "160",
            "planned_billable_utilization_pct": "0.75",
            "hourly_price": "150",
            "project_revenue": "0",
            "labor_cost_per_hour": "60",
            "contractor_cost": "0",
            "project_expenses": "500",
            "operating_expenses": "2500",
            "invoice_payment_delay_periods": 1,
            "horizon_months": 1,
            "business_goal": "Hit a 20% operating margin on a single quarter.",
        },
    },
    {
        "name": "Pioneer Distribution Co. (demo)",
        "industry": Industry.WHOLESALE.value,
        "currency": "USD",
        "min_cash_reserve": "7500",
        "target_operating_margin": "0.08",
        "max_unsold_inventory_exposure_pct": "0.30",
        "csv": "wholesale_demo.csv",
        "scenario_name": "Q1 baseline",
        "scenario_inputs": {
            "industry": "wholesale",
            "opening_cash": "25000",
            "opening_inventory_units": "500",
            "planned_purchase_units": "1500",
            "purchase_unit_cost": "7.50",
            "selling_price": "13.00",
            "expected_units_sold": "1700",
            "shrinkage_pct": "0.01",
            "operating_expenses": "4000",
            "supplier_payment_delay_periods": 1,
            "customer_payment_delay_periods": 1,
            "horizon_months": 2,
            "business_goal": "Maintain 8% operating margin with a 30-day payment cycle.",
        },
    },
    {
        "name": "Maple Street Eatery (demo)",
        "industry": Industry.FOOD.value,
        "currency": "USD",
        "min_cash_reserve": "2500",
        "target_operating_margin": "0.12",
        "max_unsold_inventory_exposure_pct": "0.15",
        "csv": "food_demo.csv",
        "scenario_name": "Q1 baseline",
        "scenario_inputs": {
            "industry": "food",
            "opening_cash": "6000",
            "opening_inventory_units": "200",
            "planned_purchase_units": "800",
            "purchase_unit_cost": "2.40",
            "selling_price": "6.50",
            "expected_units_sold": "900",
            "shrinkage_pct": "0.08",
            "operating_expenses": "1500",
            "supplier_payment_delay_periods": 0,
            "customer_payment_delay_periods": 0,
            "horizon_months": 1,
            "business_goal": "Keep unsold-inventory exposure under 15% (food is highly perishable).",
        },
    },
]


def _import_csv(db, business: Business, csv_filename: str) -> dict[str, Any]:
    path = SAMPLE_DIR / csv_filename
    content = path.read_bytes()
    headers = [h for h in content.decode("utf-8").splitlines()[0].split(",")]
    # `suggest_mapping` returns header → canonical; `parse_rows` expects the inverse
    # (canonical → source column), matching the API's commit endpoint contract.
    suggested = suggest_mapping(headers)
    mapping = {canonical: src for src, canonical in suggested.items()}
    rows, issues = parse_rows(content, mapping)
    imported = 0
    error_rows = {
        i.row for i in issues if i.severity == "error" and i.field in {"tx_date", "amount"}
    }
    for r in rows:
        if r.get("source_row") in error_rows:
            continue
        db.add(
            Transaction(
                business_id=business.id,
                tx_date=r["tx_date"],
                cash_flow_date=r.get("cash_flow_date"),
                description=r.get("description", ""),
                amount=r["amount"],
                currency=r.get("currency") or business.currency,
                direction=r["direction"],
                category=r.get("category") or "uncategorized",
                payment_status=r.get("payment_status"),
                customer_or_supplier=r.get("customer_or_supplier"),
                source_file=csv_filename,
                source_sheet=None,
                source_row=r.get("source_row"),
            )
        )
        imported += 1
    job = ImportJob(
        business_id=business.id,
        filename=csv_filename,
        file_extension=".csv",
        file_size_bytes=len(content),
        encoding="utf-8",
        sheet_name=None,
        column_mapping=json.dumps(mapping),
        row_count_total=len(rows) + len(error_rows),
        row_count_imported=imported,
        row_count_rejected=len(error_rows),
        validation_issues=json.dumps([i.to_dict() for i in issues]),
        status="committed",
    )
    db.add(job)
    db.flush()
    return {"imported": imported, "issues": len(issues), "job_id": job.id}


def _create_scenario(
    db, business: Business, name: str, inputs: dict[str, Any]
) -> Scenario:
    result = run_scenario(inputs, business.currency)
    s = Scenario(
        business_id=business.id,
        name=name,
        industry=business.industry,
        description="Auto-generated baseline scenario from the seed script.",
        status="baseline",
    )
    db.add(s)
    db.flush()
    v = ScenarioVersion(
        scenario_id=s.id,
        version_number=1,
        inputs_json=json.dumps(inputs),
        result_json=result.model_dump_json(),
        engine_version=result.engine_version,
        calculation_timestamp=result.calculation_timestamp,
    )
    db.add(v)
    db.flush()
    return s


def _seed_business(db, spec: dict[str, Any]) -> None:
    existing = (
        db.execute(
            select(Business).where(
                Business.name == spec["name"], Business.industry == spec["industry"]
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        print(f"  - skip (exists): {spec['name']}")
        return
    b = Business(
        name=spec["name"],
        industry=spec["industry"],
        currency=spec["currency"],
        fiscal_year_start_month=1,
        locale="en-US",
        min_cash_reserve=Decimal(spec["min_cash_reserve"]),
        target_operating_margin=Decimal(spec["target_operating_margin"]),
        max_unsold_inventory_exposure_pct=Decimal(spec["max_unsold_inventory_exposure_pct"]),
    )
    db.add(b)
    db.flush()
    import_summary = _import_csv(db, b, spec["csv"])
    scenario = _create_scenario(db, b, spec["scenario_name"], spec["scenario_inputs"])
    print(
        f"  + created {b.name} [{b.industry}] "
        f"(imported {import_summary['imported']} tx, "
        f"issues {import_summary['issues']}, "
        f"baseline scenario {scenario.id})"
    )


def main() -> None:
    print(f"Seeding demo data from {SAMPLE_DIR} ...")
    with SessionLocal() as db:
        for spec in DEMO_BUSINESSES:
            _seed_business(db, spec)
        db.commit()
    print("Done.")


if __name__ == "__main__":
    main()
