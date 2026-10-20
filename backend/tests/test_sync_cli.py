"""Tests for the ``scripts/sync_sources.py`` CLI.

The CLI is the Windows Task Scheduler / cron entry point, so its
argument handling and its "never print a credential" rule are worth
locking down.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The repo-root ``scripts/`` directory (next to ``backend/``).
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# The backend package must be importable for the script to import at all.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture
def clean_db(tmp_path, monkeypatch):
    """Point the session factory at an empty, migrated-style SQLite DB."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.base import Base
    import app.models  # noqa: F401
    import app.models.data_source  # noqa: F401

    db_path = tmp_path / "cli.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    import app.db.session as db_session_mod

    monkeypatch.setattr(db_session_mod, "SessionLocal", session)
    return session


def test_no_args_is_a_usage_error(clean_db, capsys) -> None:
    import sync_sources

    rc = sync_sources.main([])
    assert rc == 2


def test_list_with_no_sources_says_so(clean_db, capsys) -> None:
    import sync_sources

    rc = sync_sources.main(["--list"])
    assert rc == 0
    assert "No data sources configured" in capsys.readouterr().out


def test_list_shows_a_configured_source(clean_db, capsys) -> None:
    from decimal import Decimal

    import sync_sources
    from app.models.business import Business
    from app.models.data_source import DataSource

    db = clean_db()
    b = Business(
        name="CLI Co", industry="retail", currency="USD",
        fiscal_year_start_month=1, locale="en-US",
        min_cash_reserve=Decimal("0"),
        target_operating_margin=Decimal("0.10"),
        max_unsold_inventory_exposure_pct=Decimal("0.20"),
    )
    db.add(b)
    db.commit()
    src = DataSource(
        business_id=b.id, type="file", name="my csv",
        config='{"path": "x.csv"}', column_mapping="{}",
        schedule="manual", enabled=True, secret_ref="TOP_SECRET_DB_URL",
    )
    db.add(src)
    db.commit()
    db.close()

    rc = sync_sources.main(["--list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "my csv" in out
    # The secret env-var name must never be printed.
    assert "TOP_SECRET_DB_URL" not in out


def test_unknown_source_id_is_a_usage_error(clean_db, capsys) -> None:
    import sync_sources

    rc = sync_sources.main(["--source", "does-not-exist"])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


def test_dry_run_reports_without_writing(clean_db, capsys, tmp_path, monkeypatch) -> None:
    from decimal import Decimal

    import sync_sources
    from app.models.business import Business
    from app.models.data_source import DataSource

    db = clean_db()
    b = Business(
        name="Dry Co", industry="retail", currency="USD",
        fiscal_year_start_month=1, locale="en-US",
        min_cash_reserve=Decimal("0"),
        target_operating_margin=Decimal("0.10"),
        max_unsold_inventory_exposure_pct=Decimal("0.20"),
    )
    db.add(b)
    db.commit()
    src = DataSource(
        business_id=b.id, type="file", name="dry csv",
        config='{"path": "x.csv"}', column_mapping="{}",
        schedule="daily", enabled=True,
    )
    db.add(src)
    db.commit()
    db.close()

    rc = sync_sources.main(["--all", "--dry-run"])
    assert rc == 0
    assert "Dry run" in capsys.readouterr().out


def test_all_with_nothing_due_is_a_noop(clean_db, capsys) -> None:
    import sync_sources

    rc = sync_sources.main(["--all"])
    assert rc == 0
    assert "No sources are due" in capsys.readouterr().out