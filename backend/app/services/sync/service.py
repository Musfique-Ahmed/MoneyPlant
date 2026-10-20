"""Sync orchestration service.

Responsibilities:

1. Build the right :class:`Connector` for the source ``type``.
2. Read the rows in a streaming fashion.
3. Translate source-side field names through the user-confirmed
   ``column_mapping`` to canonical field names.
4. Validate each row through the existing engine CSV parser so the
   exact same rules apply (date formats, decimal precision,
   direction inference, currency fall-back).
5. De-duplicate against the DB using a stable SHA-256 over the
   canonical tuple (``source_row_hash``). On a unique-constraint
   conflict we count it as a duplicate, not a failure.
6. Persist only NEW valid rows inside a single transaction so a
   partial failure cannot leave the DB in a half-imported state.
7. Record a :class:`SyncRun` with the counters
   (``rows_read``, ``rows_added``, ``rows_skipped_duplicate``,
   ``rows_rejected``).
8. Update the :class:`DataSource` (last_sync_at, last_status,
   last_error_summary, incremental_value, file_content_sha256).

The service deliberately does NOT call the alerts / financing /
insights endpoints — those endpoints are request-scoped and read
straight from the DB, so the dashboard and panels refresh the next
time the client hits them.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.business import Business
from app.models.data_source import (
    DataSource,
    SCHEDULE_DAILY,
    SCHEDULE_HOURLY,
    SCHEDULE_MANUAL,
    SOURCE_TYPE_FILE,
    SOURCE_TYPE_SQL,
    STATUS_FAILED,
    STATUS_OK,
    STATUS_PARTIAL,
    SyncRun,
)
from app.models.transaction import Transaction
from app.services.ingestion.csv import (
    CANONICAL_FIELDS,
    ValidationIssue,
    parse_rows,
)
from app.services.sync.connectors import (
    ConnectorReadResult,
    row_dedup_payload,
    row_hash,
    row_natural_key,
)
from app.services.sync.file_connector import FileConnector, FileSourceError
from app.services.sync.sql_connector import SqlConnector, SqlSourceError

logger = logging.getLogger(__name__)


#: Default filesystem root used for file sources. Configurable via the
#: ``FILE_SOURCE_ROOT`` env var (or ``Settings.file_source_root``). Kept as a
#: module constant for callers that need the default without a Settings read.
DEFAULT_FILE_SOURCE_ROOT = Path(
    os.environ.get("FILE_SOURCE_ROOT")
    or (Path(__file__).resolve().parents[3] / "sample_data")
).resolve()


class SyncServiceError(Exception):
    """Raised for malformed configs / missing business / etc."""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_sync(
    db: Session,
    *,
    source_id: str,
    trigger: str,
) -> SyncRun:
    """Run the sync for a single DataSource. Returns the persisted SyncRun.

    All DB writes happen inside one ``Session.flush`` / ``commit`` cycle so
    a mid-flight error rolls back cleanly.
    """
    source = db.get(DataSource, source_id)
    if source is None:
        raise SyncServiceError(f"data_source_not_found:{source_id}")
    return _run_sync(db=db, source=source, trigger=trigger)


def run_sync_for_business(
    db: Session,
    *,
    business_id: str,
    trigger: str,
) -> list[SyncRun]:
    """Sync every enabled source for a business, in order."""
    rows = (
        db.query(DataSource)
        .filter(DataSource.business_id == business_id, DataSource.enabled.is_(True))
        .all()
    )
    return [_run_sync(db=db, source=s, trigger=trigger) for s in rows]


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _run_sync(
    db: Session, *, source: DataSource, trigger: str,
) -> SyncRun:
    business = db.get(Business, source.business_id)
    if business is None:
        return _record_failure(
            db, source, trigger, error="business_not_found",
        )
    run = SyncRun(source_id=source.id, status="running", trigger=trigger)
    db.add(run)
    db.flush()

    connector, issue_text, error_text = _build_connector(source)
    if connector is None:
        error_summary = issue_text or error_text or "connect_failed"
        run.status = STATUS_FAILED
        run.error_summary = (error_summary or "")[:500]
        run.finished_at = datetime.utcnow()
        _record_run_counters(
            run, rows_read=0, rows_added=0, rows_skipped_duplicate=0,
            rows_rejected=0, validation_issues=[],
        )
        _update_source_after_run(db, source, run, last_error_summary=error_summary)
        db.commit()
        return run

    # Read once. We do NOT iterate past a hard limit.
    try:
        if source.type == SOURCE_TYPE_FILE:
            read_result = connector.read_rows(
                previous_content_sha256=source.file_content_sha256
            )
        else:
            read_result = connector.read_rows()
    except (FileSourceError, SqlSourceError) as exc:
        run.status = STATUS_FAILED
        run.error_summary = f"read_failed: {exc}"[:500]
        run.finished_at = datetime.utcnow()
        _record_run_counters(
            run, rows_read=0, rows_added=0, rows_skipped_duplicate=0,
            rows_rejected=0, validation_issues=[],
        )
        _update_source_after_run(db, source, run, last_error_summary=str(exc))
        db.commit()
        return run
    except Exception as exc:  # noqa: BLE001
        # An unexpected driver-level failure. The message may embed the
        # connection string, so we deliberately do NOT echo it — only the
        # exception class name reaches the run record, API or logs.
        logger.warning(
            "sync.read_unexpected_error",
            extra={"source_id": source.id, "event": "read_unexpected"},
        )
        safe = f"read_failed:{type(exc).__name__}"
        run.status = STATUS_FAILED
        run.error_summary = safe[:500]
        run.finished_at = datetime.utcnow()
        _record_run_counters(
            run, rows_read=0, rows_added=0, rows_skipped_duplicate=0,
            rows_rejected=0, validation_issues=[],
        )
        _update_source_after_run(db, source, run, last_error_summary=safe)
        db.commit()
        return run

    # Map source-side header names to canonical field names.
    try:
        column_mapping = json.loads(source.column_mapping or "{}")
    except json.JSONDecodeError:
        column_mapping = {}
    # The ingestion CSV parser expects ``mapping = {canonical: source_col}``
    # like the rest of the app. The user provides it that way; we just use it.
    try:
        config_dict = json.loads(source.config or "{}")
    except json.JSONDecodeError:
        config_dict = {}

    # Materialise the already-obtained read result (the connector was read
    # once above; we must NOT re-read the source).
    rows = list(read_result.rows)

    # The connector reports a candidate watermark, but for SQL sources we
    # recompute it from the last row we actually consumed so an empty or
    # short batch can never move the cursor backwards.
    watermark_after = read_result.watermark_after
    if source.type == SOURCE_TYPE_SQL and rows and source.incremental_key:
        last_value = rows[-1].data.get(source.incremental_key)
        if last_value is not None:
            watermark_after = str(last_value)

    rows_read = len(rows)
    rows_added = 0
    rows_skipped_duplicate = 0
    rows_rejected = 0
    validation_issues: list[dict[str, Any]] = []
    affected_business_id = business.id

    # Each RawRow carries the source-side columns keyed by their ORIGINAL
    # names (e.g. "date", "amount", "type"). ``parse_rows`` resolves them
    # through ``column_mapping`` (canonical -> source), so we must hand it
    # the untouched source-side dict, not a canonicalised one.
    raw_by_source_col = [
        {k: v for k, v in r.data.items() if not k.startswith("_")}
        for r in rows
    ]

    # The parser reads ``row.get(mapping[canonical])``. The set of source
    # columns is whatever the first row actually carries; fall back to the
    # mapping's values when the batch is empty.
    source_columns = sorted(raw_by_source_col[0].keys()) if raw_by_source_col else sorted(
        set(column_mapping.values())
    )
    rows_iter = _rows_for_parser(raw_by_source_col, source_columns)

    # De-dup by source_row_hash. We check existing hashes by querying
    # before insert, and also catch unique-constraint conflicts.
    existing_hashes = _existing_hashes_for_business(db, affected_business_id)

    canonical_rows, issues = parse_rows_for_sync(
        raw_rows=rows_iter,
        mapping=column_mapping,
    )
    for issue in issues:
        if issue.severity == "error":
            rows_rejected += 1
        validation_issues.append(issue.to_dict())

    for canonical_row in canonical_rows:
        # Stable SHA-256 over the canonical tuple. This is the dedup key AND
        # the value stored in ``transactions.source_row_hash``.
        key_payload = {
            k: canonical_row.get(k) for k in CANONICAL_FIELDS if k != "source_row"
        }
        key = row_hash(
            row_natural_key(_stringify_for_key(key_payload))
        )
        if key in existing_hashes:
            rows_skipped_duplicate += 1
            continue
        existing_hashes.add(key)
        tx = Transaction(
            business_id=affected_business_id,
            tx_date=canonical_row["tx_date"],
            cash_flow_date=canonical_row.get("cash_flow_date"),
            description=canonical_row.get("description", "") or "",
            amount=str(canonical_row["amount"]),
            currency=canonical_row.get("currency") or business.currency,
            direction=canonical_row["direction"],
            category=canonical_row.get("category") or "uncategorized",
            payment_status=canonical_row.get("payment_status"),
            customer_or_supplier=canonical_row.get("customer_or_supplier"),
            source_file=(config_dict.get("path") if source.type == SOURCE_TYPE_FILE else None),
            source_sheet=(config_dict.get("sheet_name") if source.type == SOURCE_TYPE_FILE else None),
            source_row=canonical_row.get("source_row"),
            source_row_hash=key,
            data_source_id=source.id,
            import_job_id=None,
        )
        # SAVEPOINT: a unique-constraint race rolls back only this row, never
        # the enclosing transaction (and so never the watermark update).
        try:
            with db.begin_nested():
                db.add(tx)
                db.flush()
            rows_added += 1
        except IntegrityError:
            rows_skipped_duplicate += 1

    run.status = STATUS_OK if rows_rejected == 0 else STATUS_PARTIAL
    run.finished_at = datetime.utcnow()
    _record_run_counters(
        run,
        rows_read=rows_read,
        rows_added=rows_added,
        rows_skipped_duplicate=rows_skipped_duplicate,
        rows_rejected=rows_rejected,
        validation_issues=validation_issues,
    )

    # Update the source's last_* + watermark / file hash. ``watermark_after``
    # was recomputed above from the rows we actually consumed.
    _update_source_after_run(
        db, source, run,
        last_error_summary=None,
        file_content_sha256=read_result.content_sha256,
        incremental_value=watermark_after if source.type == SOURCE_TYPE_SQL else None,
        keep_existing_watermark_for_file=source.type == SOURCE_TYPE_FILE,
    )

    db.commit()
    db.refresh(run)
    # Force a lazy load on the relationship.
    _ = source.runs
    return run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_connector(
    source: DataSource,
) -> tuple[Any | None, str | None, str | None]:
    """Return ``(connector, issue_text, error_text)`` — exactly one is non-None on failure."""
    try:
        config = json.loads(source.config or "{}")
    except json.JSONDecodeError as exc:
        return None, f"invalid_config_json: {exc}", None

    if source.type == SOURCE_TYPE_FILE:
        try:
            # Read the allowed root directly from the environment so tests
            # that ``monkeypatch.setenv`` get the test value. In production
            # ``Settings.file_source_root`` is initialised from the same
            # variable, so the two paths agree.
            from app.core.config import get_settings

            try:
                settings = get_settings()
                configured = settings.file_source_root
            except Exception:  # noqa: BLE001
                configured = "./sample_data"
            root = Path(
                os.environ.get("FILE_SOURCE_ROOT", configured)
            ).resolve()
            return FileConnector(
                path=config.get("path", ""),
                sheet_name=config.get("sheet_name"),
                allowed_root=root,
            ), None, None
        except FileSourceError as exc:
            return None, str(exc), None

    if source.type == SOURCE_TYPE_SQL:
        if not source.secret_ref:
            return None, "secret_ref_required_for_sql", None
        url = os.environ.get(source.secret_ref, "")
        if not url:
            return None, f"secret_ref_unresolved:{source.secret_ref}", None
        try:
            return SqlConnector(
                url=url,
                table=config.get("table", ""),
                schema=config.get("schema"),
                incremental_key=source.incremental_key,
                row_limit=int(config.get("row_limit", 50_000)),
                statement_timeout_seconds=int(
                    config.get("statement_timeout_seconds", 30)
                ),
                previous_watermark=source.incremental_value,
            ), None, None
        except SqlSourceError as exc:
            return None, str(exc), None

    return None, f"unsupported_type:{source.type}", None


def _rows_for_parser(rows: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    """Build an array of {column: value, …} dicts (CSV-DictReader shape)."""
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows, start=2):  # start=2 matches CSV convention
        d = {c: ("" if r.get(c) is None else str(r.get(c))) for c in columns}
        out.append(d)
    return out


def parse_rows_for_sync(
    *,
    raw_rows: list[dict[str, str]],
    mapping: dict[str, str],
) -> tuple[list[dict[str, Any]], list[ValidationIssue]]:
    """Wrap :func:`app.services.ingestion.csv.parse_rows` for our pipeline.

    The CSV parser expects raw bytes; here we already have dict-of-strings
    because the connector did the parsing. We serialise to CSV in-memory
    once to reuse the validation logic verbatim. Cheap because the file is
    bounded (``upload_max_bytes`` / ``row_limit``).
    """
    import csv
    import io

    if not raw_rows:
        return [], []
    columns = list(raw_rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    for r in raw_rows:
        writer.writerow(r)
    content = buf.getvalue().encode("utf-8")
    # invert mapping: CSV parser wants canonical→source (it already does).
    return parse_rows(content, mapping)


def _existing_hashes_for_business(db: Session, business_id: str) -> set[str]:
    rows = db.execute(
        select(Transaction.source_row_hash).where(
            Transaction.business_id == business_id,
            Transaction.source_row_hash.is_not(None),
        )
    ).all()
    return {r[0] for r in rows if r[0]}


def _stringify_for_key(d: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif v is None:
            out[k] = None
        else:
            out[k] = str(v)
    return out  # type: ignore[return-value]


def _update_source_after_run(
    db: Session,
    source: DataSource,
    run: SyncRun,
    *,
    last_error_summary: str | None,
    file_content_sha256: str | None = None,
    incremental_value: str | None = None,
    keep_existing_watermark_for_file: bool = False,
) -> None:
    source.last_sync_at = run.finished_at
    source.last_status = STATUS_OK if run.status != STATUS_FAILED else STATUS_FAILED
    source.last_error_summary = last_error_summary
    if file_content_sha256 is not None:
        source.file_content_sha256 = file_content_sha256
    if incremental_value is not None and not keep_existing_watermark_for_file:
        source.incremental_value = incremental_value


def _record_run_counters(
    run: SyncRun,
    *,
    rows_read: int,
    rows_added: int,
    rows_skipped_duplicate: int,
    rows_rejected: int,
    validation_issues: list[dict[str, Any]],
) -> None:
    run.rows_read = rows_read
    run.rows_added = rows_added
    run.rows_skipped_duplicate = rows_skipped_duplicate
    run.rows_rejected = rows_rejected
    run.validation_issues = json.dumps(validation_issues, default=str)


def _record_failure(
    db: Session, source: DataSource, trigger: str, *, error: str,
) -> SyncRun:
    run = SyncRun(
        source_id=source.id, status=STATUS_FAILED, trigger=trigger,
        finished_at=datetime.utcnow(),
        error_summary=error[:500],
    )
    db.add(run)
    source.last_status = STATUS_FAILED
    source.last_error_summary = error
    source.last_sync_at = run.finished_at
    db.commit()
    return run


__all__ = [
    "run_sync",
    "run_sync_for_business",
    "SyncServiceError",
    "DEFAULT_FILE_SOURCE_ROOT",
]