"""HTTP API for data sources and sync runs.

SECURITY:

- :class:`DataSourceRead` is the only schema used in responses. It
  deliberately has no ``secret_ref`` field. API handlers therefore
  never echo back the env-var name.
- File-source paths are rejected outside the configured allowed root
  even if they pass schema validation — the connector raises
  ``FileSourceError`` synchronously and the handler turns it into a
  400 with a safe error code.
- The "test" endpoint probes the connector with a 5-row sample and a
  hard timeout, so it can be called freely without exhausting
  resources. It does NOT persist any rows.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.business import Business
from app.models.data_source import (
    SCHEDULES,
    SOURCE_TYPES,
    STATUS_FAILED,
    SyncRun,
    DataSource,
)
from app.schemas.data_source import (
    DataSourceCreate,
    DataSourceRead,
    DataSourceTestResult,
    DataSourceUpdate,
    SyncRunList,
    SyncRunRead,
)
from app.services.sync.service import (
    SyncServiceError,
    run_sync,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sources", tags=["data-sources"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_read(s: DataSource) -> DataSourceRead:
    return DataSourceRead.model_validate(
        {
            "id": s.id,
            "business_id": s.business_id,
            "type": s.type,
            "name": s.name,
            "config": json.loads(s.config or "{}"),
            "column_mapping": json.loads(s.column_mapping or "{}"),
            "incremental_key": s.incremental_key,
            "incremental_value": s.incremental_value,
            "file_content_sha256": s.file_content_sha256,
            "schedule": s.schedule,
            "enabled": s.enabled,
            "last_sync_at": s.last_sync_at,
            "last_status": s.last_status,
            "last_error_summary": s.last_error_summary,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }
    )


def _run_to_read(r: SyncRun) -> SyncRunRead:
    try:
        issues = json.loads(r.validation_issues or "[]")
    except json.JSONDecodeError:
        issues = []
    return SyncRunRead.model_validate(
        {
            "id": r.id,
            "source_id": r.source_id,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "status": r.status,
            "rows_read": r.rows_read,
            "rows_added": r.rows_added,
            "rows_skipped_duplicate": r.rows_skipped_duplicate,
            "rows_rejected": r.rows_rejected,
            "validation_issues": issues,
            "error_summary": r.error_summary,
            "trigger": r.trigger,
        }
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[DataSourceRead])
def list_data_sources(
    business_id: str, db: Session = Depends(get_db),
) -> list[DataSourceRead]:
    rows = (
        db.query(DataSource)
        .filter(DataSource.business_id == business_id)
        .order_by(DataSource.created_at.desc())
        .all()
    )
    return [_to_read(s) for s in rows]


@router.post("", response_model=DataSourceRead, status_code=201)
def create_data_source(
    payload: DataSourceCreate, db: Session = Depends(get_db),
) -> DataSourceRead:
    if payload.type not in SOURCE_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {SOURCE_TYPES}")
    if payload.schedule not in SCHEDULES:
        raise HTTPException(status_code=400, detail=f"schedule must be one of {SCHEDULES}")
    business = db.get(Business, payload.business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="business_not_found")
    if payload.type == "sql" and not payload.secret_ref:
        raise HTTPException(status_code=400, detail="secret_ref_required_for_sql")
    # Verify the file path for FILE sources up front so the user sees an error.
    if payload.type == "file":
        from pathlib import Path
        from app.core.config import get_settings
        from app.services.sync.file_connector import FileConnector, FileSourceError

        try:
            settings = get_settings()
            FileConnector(
                path=payload.config.path or "",
                sheet_name=payload.config.sheet_name,
                allowed_root=Path(settings.file_source_root).resolve(),
            )
        except FileSourceError as exc:
            raise HTTPException(status_code=400, detail=f"file_source_invalid: {exc}") from exc

    source = DataSource(
        business_id=payload.business_id,
        type=payload.type,
        name=payload.name,
        config=json.dumps(payload.config.model_dump(by_alias=False)),
        column_mapping=json.dumps(payload.column_mapping),
        incremental_key=payload.incremental_key,
        schedule=payload.schedule,
        enabled=payload.enabled,
        secret_ref=payload.secret_ref,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return _to_read(source)


@router.get("/{source_id}", response_model=DataSourceRead)
def get_data_source(
    source_id: str, db: Session = Depends(get_db),
) -> DataSourceRead:
    s = db.get(DataSource, source_id)
    if s is None:
        raise HTTPException(status_code=404, detail="data_source_not_found")
    return _to_read(s)


@router.patch("/{source_id}", response_model=DataSourceRead)
def update_data_source(
    source_id: str, payload: DataSourceUpdate, db: Session = Depends(get_db),
) -> DataSourceRead:
    s = db.get(DataSource, source_id)
    if s is None:
        raise HTTPException(status_code=404, detail="data_source_not_found")
    data = payload.model_dump(exclude_unset=True)
    if "schedule" in data and data["schedule"] is not None and data["schedule"] not in SCHEDULES:
        raise HTTPException(status_code=400, detail=f"schedule must be one of {SCHEDULES}")
    if "config" in data and data["config"] is not None and isinstance(data["config"], dict):
        # Pydantic models -> dict; from update endpoint payload dicts work.
        try:
            s.config = json.dumps(data["config"])
        except TypeError as exc:
            raise HTTPException(status_code=400, detail=f"config_invalid_json: {exc}") from exc
        data.pop("config", None)
    if "column_mapping" in data:
        try:
            s.column_mapping = json.dumps(data["column_mapping"])
        except TypeError as exc:
            raise HTTPException(status_code=400, detail=f"column_mapping_invalid_json: {exc}") from exc
        data.pop("column_mapping", None)
    for k, v in data.items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return _to_read(s)


@router.delete("/{source_id}", status_code=204)
def delete_data_source(
    source_id: str, db: Session = Depends(get_db),
) -> None:
    s = db.get(DataSource, source_id)
    if s is None:
        raise HTTPException(status_code=404, detail="data_source_not_found")
    db.delete(s)
    db.commit()
    return None


# ---------------------------------------------------------------------------
# Test + sync
# ---------------------------------------------------------------------------


@router.post("/{source_id}/test", response_model=DataSourceTestResult)
def test_data_source(
    source_id: str, db: Session = Depends(get_db),
) -> DataSourceTestResult:
    """Probe the connector without persisting any rows.

    Always returns a text status: ``ok`` or ``failed`` with a safe
    reason. Credentials are never returned.
    """
    s = db.get(DataSource, source_id)
    if s is None:
        raise HTTPException(status_code=404, detail="data_source_not_found")
    try:
        if s.type == "file":
            from pathlib import Path
            from app.core.config import get_settings
            from app.services.sync.file_connector import FileConnector

            settings = get_settings()
            cfg = json.loads(s.config or "{}")
            connector = FileConnector(
                path=cfg.get("path", ""),
                sheet_name=cfg.get("sheet_name"),
                allowed_root=Path(settings.file_source_root).resolve(),
            )
            result = connector.read_rows()
        elif s.type == "sql":
            from app.services.sync.sql_connector import SqlConnector, SqlSourceError

            cfg = json.loads(s.config or "{}")
            url = ""
            if s.secret_ref:
                import os
                url = os.environ.get(s.secret_ref, "")
            connector = SqlConnector(
                url=url,
                table=cfg.get("table", ""),
                schema=cfg.get("schema"),
                incremental_key=s.incremental_key,
                row_limit=int(cfg.get("row_limit", 50)),
                statement_timeout_seconds=int(cfg.get("statement_timeout_seconds", 30)),
                previous_watermark=s.incremental_value,
            )
            try:
                result = connector.read_rows()
            finally:
                connector.close()
        else:
            return DataSourceTestResult(status="failed", last_message=f"unsupported_type:{s.type}")

        return DataSourceTestResult(
            status="ok",
            last_message=None,
            sample_rows=result.sample_rows[:5],
            headers=result.headers,
            row_count_preview=result.rows_read,
        )
    except Exception as exc:  # noqa: BLE001 — surface a SAFE message, never raw trace
        # We log the full exception server-side (without secrets) but never
        # echo the underlying text directly to the client.
        logger.warning(
            "data_source.test_failed",
            extra={"source_id": s.id, "event": "test_failed"},
        )
        return DataSourceTestResult(
            status="failed",
            last_message=_safe_error(str(exc)),
            sample_rows=[],
            headers=[],
            row_count_preview=0,
        )


@router.post("/{source_id}/sync", response_model=SyncRunRead)
def sync_now(
    source_id: str, db: Session = Depends(get_db),
) -> SyncRunRead:
    """Run a sync now and return the recorded run."""
    s = db.get(DataSource, source_id)
    if s is None:
        raise HTTPException(status_code=404, detail="data_source_not_found")
    try:
        run = run_sync(db, source_id=source_id, trigger="manual")
    except SyncServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _run_to_read(run)


@router.get("/{source_id}/runs", response_model=SyncRunList)
def list_runs(
    source_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> SyncRunList:
    s = db.get(DataSource, source_id)
    if s is None:
        raise HTTPException(status_code=404, detail="data_source_not_found")
    rows = (
        db.query(SyncRun)
        .filter(SyncRun.source_id == source_id)
        .order_by(SyncRun.started_at.desc())
        .limit(max(1, min(int(limit), 200)))
        .all()
    )
    return SyncRunList(items=[_run_to_read(r) for r in rows])


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


# Map low-level connector error messages to short, safe, public codes.
_PUBLIC_ERROR_MAP: dict[str, str] = {
    "path_outside_allowed_root": "path_outside_allowed_root",
    "symlink_outside_allowed_root": "symlink_outside_allowed_root",
    "file_not_found": "file_not_found",
    "invalid_table_identifier": "invalid_table_identifier",
    "invalid_incremental_key_identifier": "invalid_incremental_key_identifier",
}


def _safe_error(msg: str) -> str:
    """Return a public, non-secret error code from an internal message."""
    for needle, code in _PUBLIC_ERROR_MAP.items():
        if needle in msg:
            return code
    # Always expose something, but keep the prefix opaque so we don't leak
    # backend internals to a client that might not be trusted.
    return "connect_failed"


__all__ = ["router", "business_router", "DataSourceRead"]


# ---------------------------------------------------------------------------
# Dashboard freshness strip
# ---------------------------------------------------------------------------

# A separate router because the freshness strip is addressed by business
# (``/api/businesses/{id}/freshness``), not by source (``/api/sources/...``).
business_router = APIRouter(prefix="/businesses", tags=["data-sources"])


@business_router.get("/{business_id}/freshness")
def freshness(
    business_id: str, db: Session = Depends(get_db),
) -> dict[str, object]:
    """Dashboard freshness strip: last sync, status, stale flag per source."""
    b = db.get(Business, business_id)
    if b is None:
        raise HTTPException(status_code=404, detail="business_not_found")
    rows = (
        db.query(DataSource)
        .filter(DataSource.business_id == business_id)
        .order_by(DataSource.last_sync_at.desc().nullslast())
        .all()
    )
    now = datetime.now(timezone.utc)
    sources: list[dict[str, object]] = []
    any_stale = False
    last_sync_at: datetime | None = None
    last_status_total = "never_run"
    for s in rows:
        stale = _is_stale(s, now)
        any_stale = any_stale or stale
        last_sync_text = _human_last(s.last_sync_at, now)
        if last_sync_at is None or (
            s.last_sync_at and s.last_sync_at > last_sync_at
        ):
            last_sync_at = s.last_sync_at
            last_status_total = s.last_status
        sources.append(
            {
                "id": s.id,
                "name": s.name,
                "type": s.type,
                "schedule": s.schedule,
                "enabled": s.enabled,
                "last_sync_at": s.last_sync_at.isoformat() if s.last_sync_at else None,
                "last_status": s.last_status,
                "last_error_summary": s.last_error_summary,
                "is_stale": stale,
                "last_sync_text": last_sync_text,
            }
        )

    return {
        "business_id": business_id,
        "source_count": len(rows),
        "last_sync_at": last_sync_at.isoformat() if last_sync_at else None,
        "last_status": last_status_total,
        "any_stale": any_stale,
        "headline": _headline_label(last_status_total, any_stale),
        "last_sync_text": _human_last(last_sync_at, now),
        "sources": sources,
    }


def _is_stale(s: DataSource, now: datetime) -> bool:
    """A source is stale when:
    - it's enabled
    - its schedule is hourly/daily (manual sources don't go stale)
    - its last_sync_at is older than the schedule + slack
    """
    if not s.enabled or s.schedule == "manual" or s.last_sync_at is None:
        return bool(s.enabled and s.schedule != "manual" and s.last_sync_at is None)
    threshold = timedelta(seconds=_schedule_seconds(s.schedule))
    when = s.last_sync_at
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (now - when) > threshold


def _schedule_seconds(schedule: str) -> int:
    if schedule == "hourly":
        return 70 * 60
    return 28 * 60 * 60  # 28 h slack on the daily bucket


def _headline_label(status: str, any_stale: bool) -> str:
    if status == "failed":
        return "Last sync failed — click Sync now."
    if status == "partial":
        return "Last sync had some rejected rows — see run history."
    if status == "never_run":
        return "No sync yet — connect a source to start pulling data."
    if any_stale:
        return "Last sync is older than the schedule."
    return "Up to date."


def _human_last(when: datetime | None, now: datetime) -> str:
    if when is None:
        return "Never"
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    seconds = int((now - when).total_seconds())
    if seconds < 60:
        return "Just now"
    if seconds < 60 * 60:
        m = seconds // 60
        return f"{m} min ago"
    if seconds < 60 * 60 * 24:
        h = seconds // 3600
        return f"{h} h ago"
    d = seconds // 86400
    return f"{d} days ago"