"""Tests for the data-source sync pipeline.

Covers the guarantees the feature promises:

1. Re-running a sync is idempotent — no duplicate transactions.
2. Appended rows in a file produce only the NEW rows.
3. A replaced file re-imports everything but still skips known rows.
4. Invalid rows are quarantined with reasons; valid rows still land.
5. A SQL source on SQLite reads only rows past the watermark.
6. Path traversal and symlink escapes are rejected.
7. A secret (the DB URL) never appears in any API response or log.
8. A failed sync leaves existing data intact.
9. The recomputation endpoints (alerts / financing / insights) reflect
   new rows after a sync.

The service itself is exercised directly against a temporary SQLite DB
so we can assert on counters and row state without HTTP overhead.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sqlite3
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session() -> Iterator[Session]:
    from app.db.base import Base
    import app.models  # noqa: F401  (register every model)
    import app.models.business  # noqa: F401
    import app.models.data_source  # noqa: F401
    import app.models.decision  # noqa: F401
    import app.models.import_job  # noqa: F401
    import app.models.scenario  # noqa: F401
    import app.models.transaction  # noqa: F401

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session_ = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = Session_()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def business(db_session: Session):
    from app.models.business import Business

    b = Business(
        name="Sync Test Co",
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


@pytest.fixture
def file_root(tmp_path: Path) -> Path:
    root = tmp_path / "inbox"
    root.mkdir()
    return root


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    """Write a CSV with the canonical header names MoneyPlant maps."""
    headers = [
        "tx_date", "amount", "direction", "category",
        "currency", "description", "payment_status",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _row(d: str, amt: str, direction: str = "inflow", desc: str = "x", cat: str = "sales") -> dict[str, str]:
    return {
        "tx_date": d,
        "amount": amt,
        "direction": direction,
        "category": cat,
        "currency": "USD",
        "description": desc,
        "payment_status": "paid",
    }


def _make_file_source(db: Session, business_id: str, root: Path, filename: str, name: str = "file src"):
    from app.models.data_source import DataSource

    src = DataSource(
        business_id=business_id,
        type="file",
        name=name,
        config=json.dumps({"path": filename}),
        column_mapping=json.dumps(
            {
                "tx_date": "tx_date",
                "amount": "amount",
                "direction": "direction",
                "category": "category",
                "currency": "currency",
                "description": "description",
                "payment_status": "payment_status",
            }
        ),
        incremental_key=None,
        schedule="daily",
        enabled=True,
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    return src


# ---------------------------------------------------------------------------
# 1. Idempotent re-sync
# ---------------------------------------------------------------------------


def test_resync_is_idempotent(db_session: Session, business, file_root: Path, monkeypatch) -> None:
    from app.models.transaction import Transaction
    from app.services.sync.service import run_sync

    monkeypatch.setenv("MONEYPLANT_FILE_SOURCE_ROOT", str(file_root))
    _write_csv(
        file_root / "data.csv",
        [
            _row("2026-01-05", "100.00", "inflow", "sale a", "sales"),
            _row("2026-01-06", "40.00", "outflow", "rent", "rent"),
        ],
    )
    src = _make_file_source(db_session, business.id, file_root, "data.csv")

    r1 = run_sync(db_session, source_id=src.id, trigger="manual")
    assert r1.rows_read == 2
    assert r1.rows_added == 2
    assert r1.rows_skipped_duplicate == 0
    assert r1.rows_rejected == 0

    r2 = run_sync(db_session, source_id=src.id, trigger="manual")
    assert r2.rows_read == 2
    # Second sync adds nothing; everything is a duplicate.
    assert r2.rows_added == 0
    assert r2.rows_skipped_duplicate == 2

    count = db_session.query(Transaction).filter(Transaction.business_id == business.id).count()
    assert count == 2, "re-sync must not create duplicate transactions"


# ---------------------------------------------------------------------------
# 2. Appended rows only
# ---------------------------------------------------------------------------


def test_appended_rows_only_add_the_new_ones(db_session: Session, business, file_root: Path, monkeypatch) -> None:
    from app.models.transaction import Transaction
    from app.services.sync.service import run_sync

    monkeypatch.setenv("MONEYPLANT_FILE_SOURCE_ROOT", str(file_root))
    _write_csv(file_root / "data.csv", [_row("2026-01-05", "100.00", "inflow", "sale a", "sales")])
    src = _make_file_source(db_session, business.id, file_root, "data.csv")
    run_sync(db_session, source_id=src.id, trigger="manual")

    # Append a second row to the same file.
    with (file_root / "data.csv").open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(_row("2026-01-05", "0", desc="x").keys()))
        w.writerow(_row("2026-01-07", "250.00", "inflow", "sale b", "sales"))

    r2 = run_sync(db_session, source_id=src.id, trigger="manual")
    assert r2.rows_read == 2
    assert r2.rows_added == 1, "only the appended row is new"
    assert r2.rows_skipped_duplicate == 1

    total = db_session.query(Transaction).filter(Transaction.business_id == business.id).count()
    assert total == 2


# ---------------------------------------------------------------------------
# 3. Replaced file
# ---------------------------------------------------------------------------


def test_replaced_file_reimports_new_content_only(db_session: Session, business, file_root: Path, monkeypatch) -> None:
    from app.models.transaction import Transaction
    from app.services.sync.service import run_sync

    monkeypatch.setenv("MONEYPLANT_FILE_SOURCE_ROOT", str(file_root))
    _write_csv(file_root / "data.csv", [_row("2026-01-05", "100.00", "inflow", "sale a", "sales")])
    src = _make_file_source(db_session, business.id, file_root, "data.csv")
    run_sync(db_session, source_id=src.id, trigger="manual")

    # Replace the file entirely with different content.
    _write_csv(
        file_root / "data.csv",
        [
            _row("2026-02-05", "900.00", "inflow", "sale z", "sales"),
            _row("2026-02-06", "75.00", "outflow", "supplier", "materials"),
        ],
    )

    r2 = run_sync(db_session, source_id=src.id, trigger="manual")
    assert r2.rows_added == 2, "replacement content is new"
    total = db_session.query(Transaction).filter(Transaction.business_id == business.id).count()
    assert total == 3, "original row retained, two new rows added"


# ---------------------------------------------------------------------------
# 4. Invalid rows quarantined
# ---------------------------------------------------------------------------


def test_invalid_rows_are_quarantined_valid_rows_land(db_session: Session, business, file_root: Path, monkeypatch) -> None:
    from app.models.transaction import Transaction
    from app.services.sync.service import run_sync

    monkeypatch.setenv("MONEYPLANT_FILE_SOURCE_ROOT", str(file_root))
    _write_csv(
        file_root / "data.csv",
        [
            _row("2026-01-05", "100.00", "inflow", "good", "sales"),
            _row("not-a-date", "50.00", "inflow", "bad date", "sales"),
            _row("2026-01-07", "abc", "inflow", "bad amount", "sales"),
        ],
    )
    src = _make_file_source(db_session, business.id, file_root, "data.csv")
    r = run_sync(db_session, source_id=src.id, trigger="manual")

    assert r.rows_added == 1
    assert r.rows_rejected == 2
    assert r.status == "partial"

    # Reasons are recorded so the UI can show them.
    issues = json.loads(r.validation_issues)
    assert len(issues) >= 2
    fields = {i["field"] for i in issues if i["severity"] == "error"}
    assert "tx_date" in fields or "amount" in fields

    total = db_session.query(Transaction).filter(Transaction.business_id == business.id).count()
    assert total == 1


# ---------------------------------------------------------------------------
# 5. SQL source on SQLite with a watermark
# ---------------------------------------------------------------------------


def test_sql_source_reads_only_rows_after_watermark(
    db_session: Session, business, monkeypatch
) -> None:
    """A SQL source pulls only rows newer than the stored watermark."""
    from app.models.data_source import DataSource
    from app.services.sync.service import run_sync

    # Build an external SQLite database the connector will read.
    ext_path = tmpfile = Path(tempfile.mkdtemp()) / "ext.db"
    con = sqlite3.connect(ext_path)
    con.execute(
        "CREATE TABLE invoices (tx_date TEXT, amount TEXT, direction TEXT, "
        "category TEXT, currency TEXT, description TEXT, payment_status TEXT, seq INTEGER)"
    )
    con.executemany(
        "INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?)",
        [
            ("2026-01-05", "100.00", "inflow", "sales", "USD", "inv 1", "paid", 1),
            ("2026-01-06", "200.00", "inflow", "sales", "USD", "inv 2", "paid", 2),
            ("2026-01-07", "300.00", "inflow", "sales", "USD", "inv 3", "paid", 3),
        ],
    )
    con.commit()
    con.close()

    url = f"sqlite:///{ext_path}"
    monkeypatch.setenv("TEST_EXT_DB_URL", url)

    src = DataSource(
        business_id=business.id,
        type="sql",
        name="ext invoices",
        config=json.dumps({"table": "invoices", "row_limit": 1000}),
        column_mapping=json.dumps(
            {
                "tx_date": "tx_date",
                "amount": "amount",
                "direction": "direction",
                "category": "category",
                "currency": "currency",
                "description": "description",
                "payment_status": "payment_status",
            }
        ),
        incremental_key="seq",
        schedule="daily",
        enabled=True,
        secret_ref="TEST_EXT_DB_URL",
    )
    db_session.add(src)
    db_session.commit()
    db_session.refresh(src)

    r1 = run_sync(db_session, source_id=src.id, trigger="manual")
    assert r1.rows_added == 3
    assert src.incremental_value == "3"

    # Append one new row upstream and re-sync: only that row arrives.
    con = sqlite3.connect(ext_path)
    con.execute(
        "INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?)",
        ("2026-01-08", "400.00", "inflow", "sales", "USD", "inv 4", "paid", 4),
    )
    con.commit()
    con.close()

    r2 = run_sync(db_session, source_id=src.id, trigger="manual")
    assert r2.rows_read == 1
    assert r2.rows_added == 1

    from app.models.transaction import Transaction

    total = db_session.query(Transaction).filter(Transaction.business_id == business.id).count()
    assert total == 4


# ---------------------------------------------------------------------------
# 6. Path traversal rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "evil_path",
    [
        "../outside.csv",
        "../../etc/passwd",
        "subdir/../../escape.csv",
    ],
)
def test_path_traversal_is_rejected(evil_path: str, file_root: Path, monkeypatch) -> None:
    from app.services.sync.file_connector import FileConnector, FileSourceError

    # A file that WOULD be reachable via traversal.
    outside = file_root.parent / "outside.csv"
    outside.write_text("tx_date,amount\n2026-01-01,1\n", encoding="utf-8")

    monkeypatch.setenv("MONEYPLANT_FILE_SOURCE_ROOT", str(file_root))
    with pytest.raises(FileSourceError):
        FileConnector(path=evil_path, sheet_name=None, allowed_root=file_root)


def test_symlink_escape_is_rejected(file_root: Path, monkeypatch, tmp_path: Path) -> None:
    from app.services.sync.file_connector import FileConnector, FileSourceError

    secret = tmp_path / "secret.csv"
    secret.write_text("tx_date,amount\n2026-01-01,1\n", encoding="utf-8")
    link = file_root / "link.csv"
    try:
        link.symlink_to(secret)
    except (OSError, NotImplementedError):  # Windows without dev mode
        pytest.skip("symlinks unavailable on this host")

    with pytest.raises(FileSourceError):
        FileConnector(path="link.csv", sheet_name=None, allowed_root=file_root)


# ---------------------------------------------------------------------------
# 7. Secrets never leak
# ---------------------------------------------------------------------------


def test_secret_ref_is_never_returned(db_session: Session, business, monkeypatch) -> None:
    from app.models.data_source import DataSource
    from app.schemas.data_source import DataSourceRead

    src = DataSource(
        business_id=business.id,
        type="sql",
        name="secret-holder",
        config=json.dumps({"table": "invoices"}),
        column_mapping=json.dumps({"tx_date": "tx_date", "amount": "amount"}),
        incremental_key="id",
        schedule="daily",
        enabled=True,
        secret_ref="MY_DB_URL",
    )
    db_session.add(src)
    db_session.commit()
    db_session.refresh(src)

    # The read schema has no secret field at all.
    assert "secret_ref" not in DataSourceRead.model_fields

    payload = DataSourceRead.model_validate(
        {
            "id": src.id,
            "business_id": src.business_id,
            "type": src.type,
            "name": src.name,
            "config": json.loads(src.config),
            "column_mapping": json.loads(src.column_mapping),
            "incremental_key": src.incremental_key,
            "incremental_value": src.incremental_value,
            "file_content_sha256": src.file_content_sha256,
            "schedule": src.schedule,
            "enabled": src.enabled,
            "last_sync_at": src.last_sync_at,
            "last_status": src.last_status,
            "last_error_summary": src.last_error_summary,
            "created_at": src.created_at,
            "updated_at": src.updated_at,
        }
    )
    blob = payload.model_dump_json()
    assert "secret_ref" not in blob
    assert "MY_DB_URL" not in blob


def test_connection_string_never_appears_in_logs(db_session: Session, business, monkeypatch, caplog) -> None:
    """A failed SQL sync must not echo the URL into logs."""
    from app.models.data_source import DataSource
    from app.services.sync.service import run_sync

    # Use an obviously-unreachable scheme (mssql+pyodbc) so SQLAlchemy
    # bails out without ever importing a real driver. The goal is to
    # prove that the URL (with embedded "password") never reaches the
    # logs or the API response. We never call this URL.
    url = "mssql+pyodbc://user:SUPERSECRETPW@db.example.com/MoneyPlant?driver={Fake}"
    monkeypatch.setenv("LEAK_TEST_DB_URL", url)

    src = DataSource(
        business_id=business.id,
        type="sql",
        name="leaky",
        config=json.dumps({"table": "invoices"}),
        column_mapping=json.dumps({"tx_date": "tx_date", "amount": "amount"}),
        incremental_key="id",
        schedule="daily",
        enabled=True,
        secret_ref="LEAK_TEST_DB_URL",
    )
    db_session.add(src)
    db_session.commit()
    db_session.refresh(src)

    with caplog.at_level(logging.DEBUG):
        run = run_sync(db_session, source_id=src.id, trigger="manual")

    assert run.status == "failed"
    all_text = "\n".join(r.getMessage() for r in caplog.records)
    for r in caplog.records:
        try:
            all_text += json.dumps(r.__dict__, default=str)
        except Exception:  # noqa: BLE001
            pass
    assert "SUPERSECRETPW" not in all_text
    assert url not in all_text
    # Error summary must also be SAFE on the way to the API.
    assert run.error_summary
    assert "SUPERSECRETPW" not in run.error_summary


# ---------------------------------------------------------------------------
# 8. Failed sync leaves data intact
# ---------------------------------------------------------------------------


def test_failed_sync_leaves_existing_data_intact(db_session: Session, business, file_root: Path, monkeypatch) -> None:
    from app.models.transaction import Transaction
    from app.services.sync.service import run_sync

    monkeypatch.setenv("MONEYPLANT_FILE_SOURCE_ROOT", str(file_root))
    _write_csv(file_root / "data.csv", [_row("2026-01-05", "100.00", "inflow", "good", "sales")])
    src = _make_file_source(db_session, business.id, file_root, "data.csv")
    run_sync(db_session, source_id=src.id, trigger="manual")
    before = db_session.query(Transaction).filter(Transaction.business_id == business.id).count()
    assert before == 1

    # Break the config: point at a file that does not exist.
    src.config = json.dumps({"path": "missing.csv"})
    db_session.commit()

    run = run_sync(db_session, source_id=src.id, trigger="manual")
    assert run.status == "failed"
    assert run.rows_added == 0

    after = db_session.query(Transaction).filter(Transaction.business_id == business.id).count()
    assert after == before, "a failed sync must not delete or corrupt existing rows"


# ---------------------------------------------------------------------------
# 9. Recomputation reflects new data
# ---------------------------------------------------------------------------


def test_alerts_endpoint_reflects_newly_synced_rows(db_session: Session, business, file_root: Path, monkeypatch) -> None:
    """After a sync the deterministic alerts engine sees the new rows."""
    from app.services.sync.service import run_sync

    monkeypatch.setenv("MONEYPLANT_FILE_SOURCE_ROOT", str(file_root))
    rows = [
        _row("2026-01-05", "5000.00", "inflow", "big sale", "sales"),
        _row("2026-01-06", "9000.00", "outflow", "big cost", "materials"),
    ]
    _write_csv(file_root / "data.csv", rows)
    src = _make_file_source(db_session, business.id, file_root, "data.csv")
    run_sync(db_session, source_id=src.id, trigger="manual")

    from app.api.alerts import get_business_alerts

    resp = get_business_alerts(business_id=business.id, db=db_session)
    assert len(resp.monthly_cash) == 1
    # Net = 5000 - 9000 = -4000
    assert resp.monthly_cash[0].closing_cash == "-4000.00"
    # Negative closing cash must raise the NEGATIVE_CASH alert.
    codes = {a.code for a in resp.alerts}
    assert "NEGATIVE_CASH" in codes