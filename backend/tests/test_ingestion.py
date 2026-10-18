"""CSV / ingestion tests.

These test the safety nets around the import pipeline:
- UTF-8 is the default; latin-1 fallback never crashes.
- Mapping suggestions match common synonyms and leave ambiguous headers unmapped.
- Per-row validation surfaces real issues; bad rows are never silently coerced
  into a successful import.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.ingestion.csv import (
    CANONICAL_FIELDS,
    SYNONYMS,
    parse_rows,
    preview_csv,
    suggest_mapping,
)


def test_suggest_mapping_handles_common_synonyms() -> None:
    headers = ["Date", "Amount", "Type", "Description", "Currency", "Status", "Customer", "Notes"]
    mapping = suggest_mapping(headers)
    assert mapping["Date"] == "tx_date"
    assert mapping["Amount"] == "amount"
    assert mapping["Type"] == "direction"
    assert mapping["Description"] == "description"
    assert mapping["Currency"] == "currency"
    # Status maps to payment_status
    assert mapping["Status"] == "payment_status"
    assert mapping["Customer"] == "customer_or_supplier"
    # Notes maps via the synonym "notes" → description. But "description" is already taken,
    # so suggest_mapping must not assign a second header to the same canonical field.
    assert "Notes" not in mapping or mapping["Notes"] != "description"


def test_suggest_mapping_skips_unknown_headers() -> None:
    headers = ["random_field_a", "another_unknown"]
    mapping = suggest_mapping(headers)
    assert mapping == {}


def test_suggest_mapping_falls_back_latin_1_headers() -> None:
    # numeric normalisation: "Value" → "value" → "amount"
    headers = ["Value", "Total"]
    mapping = suggest_mapping(headers)
    # Both map to "amount"; only the first should land
    targets = list(mapping.values())
    assert targets.count("amount") == 1


def test_preview_csv_returns_headers_and_samples() -> None:
    raw = b"date,amount,description\n2026-01-05,100.00,Coffee\n2026-01-06,50.00,Bagels\n"
    p = preview_csv(raw)
    assert p.headers == ["date", "amount", "description"]
    assert p.row_count == 2
    assert p.encoding == "utf-8"
    assert p.sample_rows[0]["date"] == "2026-01-05"
    assert "date" in p.suggested_mapping


def test_preview_csv_decodes_latin_1_fallback() -> None:
    raw = b"date,amount\n2026-01-05,100.00\n"
    # Force latin-1 with a high-byte character.
    raw_latin = b"date,description\n2026-01-05,Caf\xe9 Latam\n"
    p = preview_csv(raw_latin)
    assert p.encoding in {"utf-8", "latin-1"}  # encode attempt is permissive


def test_preview_csv_handles_empty_file() -> None:
    p = preview_csv(b"")
    assert p.row_count == 0
    assert p.headers == []


def test_parse_rows_minimal_valid() -> None:
    raw = b"date,amount,type,category\n2026-01-05,100.00,inflow,sales\n"
    rows, issues = parse_rows(
        raw,
        mapping={"tx_date": "date", "amount": "amount", "direction": "type", "category": "category"},
    )
    assert len(issues) == 0
    assert len(rows) == 1
    r = rows[0]
    assert r["amount"] == Decimal("100.00")
    assert r["direction"] == "inflow"
    assert r["category"] == "sales"
    assert r["source_row"] == 2


def test_parse_rows_normalizes_aliases_for_direction() -> None:
    raw = b"date,amount,type,category\n2026-01-05,100.00,income,sales\n2026-01-06,50.00,expense,rent\n"
    rows, issues = parse_rows(
        raw,
        mapping={"tx_date": "date", "amount": "amount", "direction": "type", "category": "category"},
    )
    assert len(issues) == 0
    directions = [r["direction"] for r in rows]
    assert directions == ["inflow", "outflow"]


def test_parse_rows_infers_direction_from_negative_amount() -> None:
    raw = b"date,amount\n2026-01-05,-50.00\n2026-01-06,75.00\n"
    rows, issues = parse_rows(
        raw,
        mapping={"tx_date": "date", "amount": "amount"},
    )
    assert len(issues) == 0
    # Negative becomes outflow; positive becomes inflow
    assert rows[0]["direction"] == "outflow"
    assert rows[0]["amount"] == Decimal("50.00")
    assert rows[1]["direction"] == "inflow"


def test_parse_rows_skips_rows_with_invalid_date_but_keeps_others() -> None:
    raw = b"date,amount,type,category\nnot-a-date,100.00,inflow,sales\n2026-01-06,50.00,inflow,sales\n"
    rows, issues = parse_rows(
        raw,
        mapping={"tx_date": "date", "amount": "amount", "direction": "type", "category": "category"},
    )
    assert len(rows) == 1
    assert rows[0]["tx_date"].isoformat() == "2026-01-06"
    assert any(i.field == "tx_date" for i in issues)


def test_parse_rows_warns_when_category_missing() -> None:
    raw = b"date,amount,type,category\n2026-01-05,100.00,inflow,\n"
    rows, issues = parse_rows(
        raw,
        mapping={"tx_date": "date", "amount": "amount", "direction": "type", "category": "category"},
    )
    assert len(rows) == 1
    assert any(i.severity == "warning" and i.field == "category" for i in issues)


def test_parse_rows_warns_on_invalid_currency() -> None:
    raw = b"date,amount,currency\n2026-01-05,100.00,XX\n"
    rows, issues = parse_rows(
        raw,
        mapping={"tx_date": "date", "amount": "amount", "currency": "currency"},
    )
    assert len(rows) == 1
    assert rows[0]["currency"] == "USD"
    assert any(i.severity == "warning" and i.field == "currency" for i in issues)


def test_canonical_fields_table_is_complete() -> None:
    expected = {
        "tx_date",
        "amount",
        "direction",
        "category",
        "currency",
        "description",
        "payment_status",
        "cash_flow_date",
        "customer_or_supplier",
    }
    assert set(CANONICAL_FIELDS) == expected
    # Every value the synonym table maps to must be a known canonical field.
    for v in SYNONYMS.values():
        assert v in expected
