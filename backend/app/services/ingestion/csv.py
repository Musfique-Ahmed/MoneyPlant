"""CSV ingestion.

Returns a :class:`PreviewResult` with headers, a sample of rows, and an
auto-suggested column mapping. The actual import happens in
``commit_import``.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

# Synonym table for column auto-mapping. Keys are normalized (lowercased,
# alphanumeric only) header names. Values are canonical fields.
SYNONYMS: dict[str, str] = {
    "date": "tx_date",
    "transactiondate": "tx_date",
    "invoicedate": "tx_date",
    "txdate": "tx_date",
    "amount": "amount",
    "total": "amount",
    "value": "amount",
    "transactionamount": "amount",
    "sales": "amount",  # ambiguous; user must confirm
    "revenue": "amount",  # ambiguous; user must confirm
    "expense": "amount",  # ambiguous; user must confirm
    "description": "description",
    "desc": "description",
    "memo": "description",
    "notes": "description",
    "category": "category",
    "type": "direction",
    "direction": "direction",
    "flow": "direction",
    "currency": "currency",
    "curr": "currency",
    "paymentstatus": "payment_status",
    "status": "payment_status",
    "cashflowdate": "cash_flow_date",
    "paidat": "cash_flow_date",
    "collectiondate": "cash_flow_date",
    "customer": "customer_or_supplier",
    "supplier": "customer_or_supplier",
    "vendor": "customer_or_supplier",
    "payee": "customer_or_supplier",
}


CANONICAL_FIELDS: list[str] = [
    "tx_date",
    "amount",
    "direction",
    "category",
    "currency",
    "description",
    "payment_status",
    "cash_flow_date",
    "customer_or_supplier",
]


def _normalize_header(h: str) -> str:
    return "".join(c.lower() for c in h if c.isalnum())


@dataclass
class ValidationIssue:
    row: int
    field: str
    severity: str  # "error" | "warning"
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"row": self.row, "field": self.field, "severity": self.severity, "message": self.message}


@dataclass
class PreviewResult:
    headers: list[str]
    sample_rows: list[dict[str, str]]
    suggested_mapping: dict[str, str]
    row_count: int
    encoding: str
    issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "headers": self.headers,
            "sample_rows": self.sample_rows,
            "suggested_mapping": self.suggested_mapping,
            "row_count": self.row_count,
            "encoding": self.encoding,
            "issues": [i.to_dict() for i in self.issues],
        }


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    """Suggest a canonical field for each header. Ambiguous headers are left unmapped."""
    out: dict[str, str] = {}
    for h in headers:
        key = _normalize_header(h)
        canonical = SYNONYMS.get(key)
        if canonical and canonical not in out.values():
            out[h] = canonical
    return out


def preview_csv(content: bytes, max_rows: int = 50) -> PreviewResult:
    """Return a preview of the CSV. Tries utf-8, then latin-1 as a fallback."""
    text: str
    encoding = "utf-8"
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        encoding = "latin-1"
        text = content.decode("latin-1", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    sample_rows: list[dict[str, str]] = []
    issues: list[ValidationIssue] = []
    total = 0
    for i, row in enumerate(reader, start=2):  # start=2 to match spreadsheet row numbers (header is row 1)
        total += 1
        if i - 2 < max_rows:
            sample_rows.append({k: (v or "") for k, v in row.items()})
    return PreviewResult(
        headers=headers,
        sample_rows=sample_rows,
        suggested_mapping=suggest_mapping(headers),
        row_count=total,
        encoding=encoding,
        issues=issues,
    )


def _parse_date(value: str) -> date | None:
    from datetime import datetime

    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(value: str) -> Decimal | None:
    value = (value or "").strip().replace(",", "")
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def parse_rows(
    content: bytes,
    mapping: dict[str, str],
) -> tuple[list[dict[str, Any]], list[ValidationIssue]]:
    """Parse a CSV given a user-confirmed column mapping. Returns (rows, issues)."""
    text: str
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    issues: list[ValidationIssue] = []
    for i, row in enumerate(reader, start=2):
        tx_date = _parse_date(row.get(mapping.get("tx_date", ""), ""))
        if tx_date is None:
            issues.append(
                ValidationIssue(row=i, field="tx_date", severity="error", message="Invalid or missing date")
            )
            continue
        amount = _parse_decimal(row.get(mapping.get("amount", ""), ""))
        if amount is None:
            issues.append(
                ValidationIssue(row=i, field="amount", severity="error", message="Invalid or missing amount")
            )
            continue
        direction = (row.get(mapping.get("direction", ""), "") or "").strip().lower()
        if direction not in {"inflow", "outflow", "income", "expense", "credit", "debit"}:
            # Try to infer from sign: positive => inflow, negative => outflow.
            if amount < 0:
                direction = "outflow"
                amount = -amount
            else:
                direction = "inflow"
        elif direction in {"income", "credit"}:
            direction = "inflow"
        elif direction in {"expense", "debit"}:
            direction = "outflow"

        # Only warn about missing category if the user actually mapped a category column.
        # If no `category` mapping is provided at all, the engine's "uncategorized" default
        # is intentional — no warning needed.
        category_col = mapping.get("category", "")
        if category_col:
            category = (row.get(category_col, "") or "").strip().lower() or "uncategorized"
            if category == "uncategorized":
                issues.append(
                    ValidationIssue(
                        row=i, field="category", severity="warning", message="Category missing; defaulted to 'uncategorized'."
                    )
                )
        else:
            category = "uncategorized"
        currency = (row.get(mapping.get("currency", ""), "") or "USD").strip().upper()
        if len(currency) != 3:
            currency = "USD"
            issues.append(
                ValidationIssue(row=i, field="currency", severity="warning", message="Currency code invalid; defaulted to USD.")
            )
        description = (row.get(mapping.get("description", ""), "") or "").strip()
        payment_status = (row.get(mapping.get("payment_status", ""), "") or "").strip().lower() or None
        if payment_status and payment_status not in {"paid", "pending", "partial"}:
            payment_status = None
        cash_flow_date_raw = (row.get(mapping.get("cash_flow_date", ""), "") or "").strip()
        cash_flow_date = _parse_date(cash_flow_date_raw) if cash_flow_date_raw else None
        customer_or_supplier = (row.get(mapping.get("customer_or_supplier", ""), "") or "").strip() or None

        rows.append(
            {
                "tx_date": tx_date,
                "cash_flow_date": cash_flow_date,
                "description": description,
                "amount": amount,
                "currency": currency,
                "direction": direction,
                "category": category,
                "payment_status": payment_status,
                "customer_or_supplier": customer_or_supplier,
                "source_row": i,
            }
        )

    return rows, issues


__all__ = [
    "PreviewResult",
    "ValidationIssue",
    "SYNONYMS",
    "CANONICAL_FIELDS",
    "preview_csv",
    "parse_rows",
    "suggest_mapping",
]