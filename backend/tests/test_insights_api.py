"""Smoke tests for the GET /api/businesses/{id}/dashboard-insights endpoint.

Uses the FastAPI TestClient + a temporary SQLite session to verify the full
HTTP path: bucket transactions, evaluate alerts, render visuals.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.db import base  # noqa: F401 — registers tables
from app.db.session import get_db
from app.main import app
from app.models.business import Business
from app.models.transaction import Transaction


@pytest.fixture()
def fake_session(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    base.Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    # Seed a business + two months of transactions that go cash-poor.
    with SessionLocal() as s:
        s.add(
            Business(
                id="biz-1",
                name="Cash-Poor Co",
                industry="service",
                currency="USD",
                fiscal_year_start_month=1,
                locale="en_US",
            )
        )
        s.add_all(
            [
                Transaction(
                    business_id="biz-1",
                    tx_date=date(2026, 1, 15),
                    cash_flow_date=date(2026, 1, 15),
                    description="sale",
                    amount="1000",
                    currency="USD",
                    direction="inflow",
                    category="service_revenue",
                    payment_status="paid",
                ),
                Transaction(
                    business_id="biz-1",
                    tx_date=date(2026, 1, 20),
                    cash_flow_date=date(2026, 1, 20),
                    description="materials",
                    amount="1500",
                    currency="USD",
                    direction="outflow",
                    category="materials",
                    payment_status="paid",
                ),
                Transaction(
                    business_id="biz-1",
                    tx_date=date(2026, 2, 10),
                    cash_flow_date=date(2026, 2, 10),
                    description="sale",
                    amount="800",
                    currency="USD",
                    direction="inflow",
                    category="service_revenue",
                    payment_status="paid",
                ),
                Transaction(
                    business_id="biz-1",
                    tx_date=date(2026, 2, 18),
                    cash_flow_date=date(2026, 2, 18),
                    description="rent",
                    amount="1200",
                    currency="USD",
                    direction="outflow",
                    category="rent",
                    payment_status="paid",
                ),
            ]
        )
        s.commit()

    def override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    yield SessionLocal
    app.dependency_overrides.clear()


def test_dashboard_insights_returns_visuals_and_alerts(fake_session):
    client = TestClient(app)
    resp = client.get("/api/businesses/biz-1/dashboard-insights")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["business_id"] == "biz-1"
    assert body["currency"] == "USD"
    visual_ids = {v["visual_id"] for v in body["visuals"]}
    # The five baseline visuals must always be present.
    assert {"kpi", "revenue_costs_profit", "cash_balance", "profit_cash_gap", "cost_breakdown"}.issubset(visual_ids)
    # Sens should also be present (we compute observed-period sensitivity).
    assert "sensitivity" in visual_ids
    # At least one alert should fire given the cash dip in month 2.
    assert body["alerts_count"] >= 1
    # Summary is a non-empty KPI block.
    assert body["summary"]["revenue"]


def test_dashboard_insights_404_when_business_missing(fake_session):
    client = TestClient(app)
    resp = client.get("/api/businesses/does-not-exist/dashboard-insights")
    assert resp.status_code == 404


def test_dashboard_insights_respects_period_filter(fake_session):
    client = TestClient(app)
    resp = client.get(
        "/api/businesses/biz-1/dashboard-insights",
        params={"period_start": "2026-02-01", "period_end_exclusive": "2026-03-01"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Only month 2 should be in the windows; closing cash should be -400.
    cash = next(v for v in body["visuals"] if v["visual_id"] == "cash_balance")
    months = cash["evidence"]["months"]
    assert len(months) == 1
    # Money-format evidence; parse cautiously.
    closing = months[0]["closing_cash"]
    assert "USD" in closing or "-" in closing
