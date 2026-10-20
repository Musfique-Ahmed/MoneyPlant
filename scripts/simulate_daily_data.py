"""Append a day of synthetic transactions to a sample database + Excel file.

Used by the demo to show "new data arriving" between syncs:

- The SQLite file (``sample_data/ext_invoices.db``) is appended with
  new rows in the ``invoices`` table. It is the same file the SQL
  source connector points at.
- The Excel file (``sample_data/daily_transactions.xlsx``) is created
  the first time and appended on every subsequent run. It is the file
  the file-source connector points at.

Run from the repo root:

    python scripts/simulate_daily_data.py

If the file or DB already has data, this script appends one new day.
If neither exists, the script creates both with a small but realistic
seed first so the demo works on a fresh checkout.

The data is SYNTHETIC. Numbers are computed deterministically (based
on the day-of-month) so successive runs produce different amounts but
the same shape.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import openpyxl

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = REPO_ROOT / "sample_data"
DB_PATH = SAMPLE_DIR / "ext_invoices.db"
XLSX_PATH = SAMPLE_DIR / "daily_transactions.xlsx"


def _next_unused_day(conn: sqlite3.Connection) -> date:
    """Pick a date one day after the most recent row, or today."""
    cur = conn.execute("SELECT MAX(tx_date) FROM invoices")
    row = cur.fetchone()
    last = row[0] if row and row[0] else None
    if last is None:
        return date(2026, 1, 5)
    last = date.fromisoformat(last)
    return last + timedelta(days=1)


def _ensure_db() -> sqlite3.Connection:
    """Create the external SQLite DB + ``invoices`` table if missing."""
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS invoices ("
        "  seq INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  tx_date TEXT NOT NULL,"
        "  amount TEXT NOT NULL,"
        "  direction TEXT NOT NULL,"
        "  category TEXT NOT NULL,"
        "  currency TEXT NOT NULL,"
        "  description TEXT NOT NULL,"
        "  payment_status TEXT NOT NULL"
        ")"
    )
    conn.commit()
    return conn


def _seed_legacy_rows(conn: sqlite3.Connection, days: int = 5) -> int:
    """Insert a small back-history on a fresh DB."""
    today = date(2026, 1, 4)
    rows_added = 0
    for offset in range(1, days + 1):
        d = today + timedelta(days=offset)
        for ttype in (
            ("inflow", "sales", "250.00"),
            ("inflow", "service_revenue", "125.00"),
            ("outflow", "materials", "-90.00"),
        ):
            direction, category, base_amt = ttype
            amount = (
                Decimal(base_amt)
                + Decimal(d.day) * Decimal("1.5")
            )
            conn.execute(
                "INSERT INTO invoices"
                " (tx_date, amount, direction, category, currency, description, payment_status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    d.isoformat(),
                    str(abs(amount)) if direction == "inflow" else "-" + str(abs(amount)),
                    direction,
                    category,
                    "USD",
                    f"synthetic {category} {d.isoformat()}",
                    "paid",
                ),
            )
            rows_added += 1
    conn.commit()
    return rows_added


def append_day_to_db(conn: sqlite3.Connection, target_day: date) -> int:
    """Append 3-5 transactions for ``target_day``. Deterministic shape."""
    added = 0
    plan = [
        ("inflow", "sales", Decimal("280.00") + Decimal(target_day.day) * Decimal("2.5")),
        ("inflow", "service_revenue", Decimal("150.00") + Decimal(target_day.day) * Decimal("1.25")),
        ("outflow", "materials", Decimal("95.00") + Decimal(target_day.day) * Decimal("0.8")),
        ("outflow", "rent", Decimal("2000.00")),
    ]
    for direction, category, amount in plan:
        signed = amount if direction == "inflow" else -amount
        conn.execute(
            "INSERT INTO invoices"
            " (tx_date, amount, direction, category, currency, description, payment_status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                target_day.isoformat(),
                f"{signed:.2f}",
                direction,
                category,
                "USD",
                f"synthetic {category} {target_day.isoformat()}",
                "paid",
            ),
        )
        added += 1
    conn.commit()
    return added


def append_day_to_xlsx(target_day: date) -> int:
    """Mirror the day's transactions into an XLSX for the file-source demo."""
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    if not XLSX_PATH.exists():
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "transactions"
        ws.append(
            [
                "tx_date", "amount", "direction", "category",
                "currency", "description", "payment_status",
            ]
        )
    else:
        wb = openpyxl.load_workbook(XLSX_PATH)
        ws = wb["transactions"]

    plan = [
        ("inflow", "sales", 275.00),
        ("inflow", "service_revenue", 145.00),
        ("outflow", "materials", -90.00),
        ("outflow", "rent", -2000.00),
    ]
    for direction, category, amount in plan:
        ws.append(
            [
                target_day.isoformat(),
                abs(amount) if direction == "inflow" else -abs(amount),
                direction,
                category,
                "USD",
                f"synthetic {category} {target_day.isoformat()}",
                "paid",
            ]
        )
    wb.save(XLSX_PATH)
    return len(plan)


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    fresh = "--fresh" in argv

    conn = _ensure_db()
    try:
        cur = conn.execute("SELECT COUNT(*) FROM invoices")
        row_count = cur.fetchone()[0]
        if row_count == 0 or fresh:
            seeded = _seed_legacy_rows(conn, days=5)
            print(f"Seeded {seeded} legacy rows into {DB_PATH}.")
        target_day = _next_unused_day(conn)
        db_added = append_day_to_db(conn, target_day)
        xlsx_added = append_day_to_xlsx(target_day)
        print(
            f"Appended day {target_day.isoformat()}: "
            f"{db_added} rows into {DB_PATH.name}; "
            f"{xlsx_added} rows into {XLSX_PATH.name}."
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())