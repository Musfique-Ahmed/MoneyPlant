"""Tests for the background scheduler's due logic.

The scheduler itself is a thin daemon thread around
``run_due_sources``. These tests cover the deterministic part: which
sources are due, and that a tick only touches due sources.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def db_session() -> Iterator[Session]:
    from app.db.base import Base
    import app.models  # noqa: F401
    import app.models.business  # noqa: F401
    import app.models.data_source  # noqa: F401
    import app.models.decision  # noqa: F401
    import app.models.import_job  # noqa: F401
    import app.models.scenario  # noqa: F401
    import app.models.transaction  # noqa: F401

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    S = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = S()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def business(db_session: Session):
    from app.models.business import Business
    from decimal import Decimal

    b = Business(
        name="Scheduler Test Co",
        industry="retail",
        currency="USD",
        fiscal_year_start_month=1,
        locale="en-US",
        min_cash_reserve=Decimal("0"),
        target_operating_margin=Decimal("0.10"),
        max_unsold_inventory_exposure_pct=Decimal("0.20"),
    )
    db_session.add(b)
    db_session.commit()
    db_session.refresh(b)
    return b


def _src(business_id: str, schedule: str, *, enabled=True, last_sync_at=None):
    from app.models.data_source import DataSource

    return DataSource(
        business_id=business_id,
        type="file",
        name=f"{schedule}-{enabled}",
        config="{}",
        column_mapping="{}",
        schedule=schedule,
        enabled=enabled,
        last_sync_at=last_sync_at,
    )


NOW = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def test_never_synced_source_is_due(db_session: Session, business) -> None:
    from app.services.sync.scheduler import is_due

    s = _src(business.id, "daily")
    assert is_due(s, NOW) is True


def test_freshly_synced_daily_source_is_not_due(db_session: Session, business) -> None:
    from app.services.sync.scheduler import is_due

    s = _src(business.id, "daily", last_sync_at=NOW - timedelta(hours=2))
    assert is_due(s, NOW) is False


def test_stale_daily_source_is_due(db_session: Session, business) -> None:
    from app.services.sync.scheduler import is_due

    s = _src(business.id, "daily", last_sync_at=NOW - timedelta(hours=29))
    assert is_due(s, NOW) is True


def test_freshly_synced_hourly_source_is_not_due(db_session: Session, business) -> None:
    from app.services.sync.scheduler import is_due

    s = _src(business.id, "hourly", last_sync_at=NOW - timedelta(minutes=10))
    assert is_due(s, NOW) is False


def test_stale_hourly_source_is_due(db_session: Session, business) -> None:
    from app.services.sync.scheduler import is_due

    s = _src(business.id, "hourly", last_sync_at=NOW - timedelta(minutes=71))
    assert is_due(s, NOW) is True


def test_manual_source_is_never_due(db_session: Session, business) -> None:
    from app.services.sync.scheduler import is_due

    s = _src(business.id, "manual", last_sync_at=None)
    assert is_due(s, NOW) is False


def test_disabled_source_is_never_due(db_session: Session, business) -> None:
    from app.services.sync.scheduler import is_due

    s = _src(business.id, "daily", enabled=False, last_sync_at=None)
    assert is_due(s, NOW) is False


def test_naive_timestamp_is_treated_as_utc(db_session: Session, business) -> None:
    from app.services.sync.scheduler import is_due

    # SQLite gives back naive datetimes; the predicate must not crash.
    s = _src(business.id, "daily", last_sync_at=datetime(2026, 2, 28, 0, 0))
    assert is_due(s, NOW) is True


def test_due_sources_filters_and_orders(db_session: Session, business) -> None:
    from app.services.sync.scheduler import due_sources

    stale = _src(business.id, "daily", last_sync_at=NOW - timedelta(hours=48))
    fresh = _src(business.id, "daily", last_sync_at=NOW - timedelta(hours=1))
    manual = _src(business.id, "manual")
    db_session.add_all([stale, fresh, manual])
    db_session.commit()

    result = due_sources(db_session, NOW)
    assert [s.id for s in result] == [stale.id]


def test_run_due_sources_only_touches_due_sources(
    db_session: Session, business, tmp_path, monkeypatch
) -> None:
    """A tick syncs the due source and leaves the fresh one alone."""
    from app.services.sync.scheduler import run_due_sources

    root = tmp_path / "inbox"
    root.mkdir()

    headers = [
        "tx_date", "amount", "direction", "category",
        "currency", "description", "payment_status",
    ]
    with (root / "due.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=headers)
        w.writeheader()
        w.writerow({
            "tx_date": "2026-02-01", "amount": "100.00", "direction": "inflow",
            "category": "sales", "currency": "USD", "description": "x",
            "payment_status": "paid",
        })

    mapping = json.dumps({
        "tx_date": "tx_date", "amount": "amount", "direction": "direction",
        "category": "category", "currency": "currency",
        "description": "description", "payment_status": "payment_status",
    })

    due = _src(business.id, "daily", last_sync_at=NOW - timedelta(hours=48))
    due.name = "due"
    due.config = json.dumps({"path": "due.csv"})
    due.column_mapping = mapping

    fresh = _src(business.id, "daily", last_sync_at=NOW - timedelta(hours=1))
    fresh.name = "fresh"

    db_session.add_all([due, fresh])
    db_session.commit()

    monkeypatch.setenv("MONEYPLANT_FILE_SOURCE_ROOT", str(root))

    factory = db_session.get_bind  # placeholder; replaced below
    started = run_due_sources(lambda: db_session, now=NOW)

    assert started == 1

    from app.models.transaction import Transaction

    assert db_session.query(Transaction).count() == 1


def test_scheduler_run_once_uses_the_same_logic(db_session: Session, business) -> None:
    from app.services.sync.scheduler import SyncScheduler

    sched = SyncScheduler(lambda: db_session, interval_seconds=30)
    # No due sources at all -> zero work, no exception.
    assert sched.run_once() == 0


def test_scheduler_floors_the_interval() -> None:
    from app.services.sync.scheduler import SyncScheduler

    sched = SyncScheduler(lambda: None, interval_seconds=1)
    assert sched._interval == 30