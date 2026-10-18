"""Import endpoints — preview, validate, commit, list, retrieve.

The flow is intentionally three steps so the UI can show the user the
preview, the suggested column mapping, the per-row validation issues,
and let them confirm before any DB write happens.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.business import Business
from app.models.import_job import ImportJob
from app.models.transaction import Transaction
from app.schemas.ingestion import ImportJobRead, ImportPreview, ImportRow
from app.services.ingestion.csv import (
    CANONICAL_FIELDS,
    ValidationIssue,
    parse_rows,
    preview_csv,
)
from app.services.ingestion.xlsx import preview_xlsx

router = APIRouter(prefix="/imports", tags=["imports"])


# --- helpers --------------------------------------------------------------


def _ext(filename: str) -> str:
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


def _preview_payload(ext: str, content: bytes) -> dict[str, Any]:
    if ext == ".csv":
        return preview_csv(content).to_dict()
    if ext in {".xlsx", ".xls"}:
        return preview_xlsx(content)
    raise HTTPException(status_code=400, detail=f"unsupported_extension: {ext}")


def _issues_json(issues: list[ValidationIssue]) -> str:
    return json.dumps([i.to_dict() for i in issues])


def _mapping_json(mapping: dict[str, str]) -> str:
    return json.dumps(mapping)


def _job_to_read(j: ImportJob) -> ImportJobRead:
    return ImportJobRead.model_validate(
        {
            "id": j.id,
            "business_id": j.business_id,
            "filename": j.filename,
            "file_extension": j.file_extension,
            "file_size_bytes": j.file_size_bytes,
            "encoding": j.encoding,
            "sheet_name": j.sheet_name,
            "column_mapping": json.loads(j.column_mapping or "{}"),
            "row_count_total": j.row_count_total,
            "row_count_imported": j.row_count_imported,
            "row_count_rejected": j.row_count_rejected,
            "validation_issues": json.loads(j.validation_issues or "[]"),
            "status": j.status,
            "created_at": j.created_at,
        }
    )


# --- routes ---------------------------------------------------------------


@router.post("/preview", response_model=ImportPreview)
async def preview(
    file: UploadFile = File(...), db: Session = Depends(get_db)  # noqa: ARG001
) -> ImportPreview:
    """Parse headers + sample rows, return suggested column mapping."""
    settings = get_settings()
    content = await file.read()
    if len(content) > settings.upload_max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"file_too_large: {len(content)} > {settings.upload_max_bytes}",
        )
    ext = _ext(file.filename or "")
    if ext not in settings.upload_allowed_extensions:
        raise HTTPException(status_code=400, detail=f"unsupported_extension: {ext}")
    payload = _preview_payload(ext, content)
    return ImportPreview(
        filename=file.filename or "",
        file_extension=ext,
        file_size_bytes=len(content),
        encoding=payload.get("encoding", "binary"),
        sheet_name=payload.get("sheet_name"),
        headers=payload.get("headers", []),
        sample_rows=payload.get("sample_rows", []),
        row_count=payload.get("row_count", 0),
        suggested_mapping=payload.get("suggested_mapping", {}),
        issues=[ImportRow(**i) for i in payload.get("issues", [])],
    )


@router.post("/validate")
async def validate(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    db: Session = Depends(get_db),  # noqa: ARG001
) -> dict[str, Any]:
    """Parse the whole file with the given mapping, return issues without writing."""
    settings = get_settings()
    content = await file.read()
    if len(content) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="file_too_large")
    ext = _ext(file.filename or "")
    if ext not in settings.upload_allowed_extensions:
        raise HTTPException(status_code=400, detail=f"unsupported_extension: {ext}")
    if ext != ".csv":
        # XLSX validation is preview-only in this MVP (no commit yet).
        return {"status": "preview_only", "issues": []}
    try:
        user_mapping = json.loads(mapping)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid_mapping_json: {exc}") from exc
    if not isinstance(user_mapping, dict):
        raise HTTPException(status_code=400, detail="mapping must be a JSON object")
    rows, issues = parse_rows(content, user_mapping)
    return {
        "status": "validated",
        "row_count": len(rows),
        "issues": [i.to_dict() for i in issues],
    }


@router.post("/commit", response_model=ImportJobRead, status_code=status.HTTP_201_CREATED)
async def commit(
    file: UploadFile = File(...),
    business_id: str = Form(...),
    mapping: str = Form(...),
    db: Session = Depends(get_db),
) -> ImportJobRead:
    """Commit the rows to the database, creating an :class:`ImportJob`."""
    settings = get_settings()
    business = db.get(Business, business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="business_not_found")

    content = await file.read()
    if len(content) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="file_too_large")
    ext = _ext(file.filename or "")
    if ext not in settings.upload_allowed_extensions:
        raise HTTPException(status_code=400, detail=f"unsupported_extension: {ext}")

    try:
        user_mapping = json.loads(mapping)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid_mapping_json: {exc}") from exc
    if not isinstance(user_mapping, dict):
        raise HTTPException(status_code=400, detail="mapping must be a JSON object")

    if ext == ".csv":
        rows, issues = parse_rows(content, user_mapping)
    else:
        # MVP: only CSV is committed.
        raise HTTPException(status_code=400, detail="xlsx_commit_not_supported_in_mvp")

    # Determine which source_rows are "error" rejections (vs warnings).
    error_rows: set[int] = {
        i.row
        for i in issues
        if i.severity == "error" and i.field in {"tx_date", "amount"}
    }

    imported = 0
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
                source_file=file.filename,
                source_sheet=None,
                source_row=r.get("source_row"),
                import_job_id=None,  # back-filled after commit
            )
        )
        imported += 1

    # Count rejected rows: error-severity issues each represent one rejected row.
    # (Warning-severity issues don't cause rejection — the row is still imported.)
    rejected = sum(1 for i in issues if i.severity == "error")
    # `row_count_total` is the rows the user submitted (valid + invalid).
    row_count_total = imported + rejected

    job = ImportJob(
        business_id=business.id,
        filename=file.filename or "",
        file_extension=ext,
        file_size_bytes=len(content),
        encoding="utf-8" if ext == ".csv" else "binary",
        sheet_name=None,
        column_mapping=_mapping_json(user_mapping),
        row_count_total=row_count_total,
        row_count_imported=imported,
        row_count_rejected=rejected,
        validation_issues=_issues_json(issues),
        status="committed",
    )
    db.add(job)
    db.flush()  # assigns job.id

    db.query(Transaction).filter(
        Transaction.business_id == business.id,
        Transaction.source_file == file.filename,
        Transaction.import_job_id.is_(None),
    ).update({Transaction.import_job_id: job.id}, synchronize_session=False)
    db.commit()
    db.refresh(job)
    return _job_to_read(job)


@router.get("", response_model=list[ImportJobRead])
def list_imports(business_id: str, db: Session = Depends(get_db)) -> list[ImportJobRead]:
    rows = (
        db.query(ImportJob)
        .filter(ImportJob.business_id == business_id)
        .order_by(ImportJob.created_at.desc())
        .all()
    )
    return [_job_to_read(j) for j in rows]


@router.get("/{job_id}", response_model=ImportJobRead)
def get_import(job_id: str, db: Session = Depends(get_db)) -> ImportJobRead:
    j = db.get(ImportJob, job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="import_not_found")
    return _job_to_read(j)


@router.get("/fields/canonical", response_model=list[str])
def canonical_fields() -> list[str]:
    """The set of canonical fields the user can map their columns to."""
    return list(CANONICAL_FIELDS)


__all__ = ["router"]
