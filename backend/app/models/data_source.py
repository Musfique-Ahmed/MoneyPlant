"""DataSource: a configured external source of transactions.

A DataSource describes HOW MoneyPlant pulls new data for a business:

- ``type``: ``file`` (CSV/XLSX under an allowed root) or ``sql``
  (read a single table/view from a SQLAlchemy URL — the connection
  string itself is referenced by env var, never stored here).
- ``config``: non-secret settings (file path, table name, column mapping,
  incremental watermark column, schedule, row limit).
- ``secret_ref``: env-var name that resolves to the DB connection URL.
  Never echoed through the API and never logged.
- ``column_mapping``: keyed by canonical field name (same set the manual
  import pipeline uses), values are the source-side column names.
- ``incremental_key``: name of a column on the source side used as a
  cursor (e.g. ``updated_at`` for SQL, file row count + content hash
  for files). For files we also use row-level hashes as a fallback so
  appends are detected even without a watermark.

State:

- ``last_sync_at``: when the last sync attempt completed.
- ``last_status``: ``ok`` | ``partial`` | ``failed`` | ``never_run``. Text
  labels are surfaced everywhere; the UI never relies on colour alone.
- ``last_error_summary``: short text reason for the last failure
  (safe to surface — redact policy in :mod:`app.core.logging`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


# Allowed source types — kept on the model so a typo in the API returns
# a 422 instead of a silent misconfiguration.
SOURCE_TYPE_FILE = "file"
SOURCE_TYPE_SQL = "sql"
SOURCE_TYPES: tuple[str, ...] = (SOURCE_TYPE_FILE, SOURCE_TYPE_SQL)

SCHEDULE_MANUAL = "manual"
SCHEDULE_HOURLY = "hourly"
SCHEDULE_DAILY = "daily"
SCHEDULES: tuple[str, ...] = (SCHEDULE_MANUAL, SCHEDULE_HOURLY, SCHEDULE_DAILY)

STATUS_NEVER_RUN = "never_run"
STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"
SYNC_STATUSES: tuple[str, ...] = (
    STATUS_NEVER_RUN,
    STATUS_OK,
    STATUS_PARTIAL,
    STATUS_FAILED,
)


class DataSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "data_sources"

    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # ``config`` is a JSON blob of non-secret settings.
    # Typical keys:
    #   file: {"path": "...", "sheet_name": "...", "row_hash_window": 1024}
    #   sql:  {"table": "public.invoices", "schema": "public",
    #          "statement_timeout_seconds": 30, "row_limit": 50000}
    config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # ``column_mapping`` is a JSON blob keyed by canonical field name. Values
    # are the source-side column names. Mirrors the manual import pipeline.
    column_mapping: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # ``incremental_key`` names the column to use as a cursor on the source side.
    # For SQL: typically "updated_at" (a timestamp column) or "id" (an integer pk).
    # For files: ignored — file sync uses a content hash + per-row hash instead.
    incremental_key: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Persisted last-value of the incremental column. Null means "first sync"
    # or "no watermark". For a file source this is ignored.
    incremental_value: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # File source content hash, persisted across syncs to detect when a
    # file was replaced vs appended. For SQL sources this is unused.
    file_content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    schedule: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SCHEDULE_DAILY,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
    )

    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_NEVER_RUN,
    )
    last_error_summary: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
    )

    # ``secret_ref`` is the NAME of an environment variable that holds the DB
    # connection URL. Never the URL itself. Empty for file sources. Not
    # returned by the API. Not logged.
    secret_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)

    business = relationship("Business", back_populates="data_sources")
    runs = relationship(
        "SyncRun",
        back_populates="source",
        cascade="all, delete-orphan",
        order_by="SyncRun.started_at.desc()",
    )


class SyncRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sync_runs"

    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    rows_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_skipped_duplicate: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    rows_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # JSON array of {row, field, severity, message}; kept verbatim for the UI.
    validation_issues: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]",
    )
    # Short, safe error description. Never includes raw row text or credentials.
    error_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Trigger that initiated the run: "manual" (button or API call),
    # "schedule" (background scheduler), "cli" (CLI invocation).
    trigger: Mapped[str] = mapped_column(
        String(16), nullable=False, default="manual",
    )

    source = relationship("DataSource", back_populates="runs")


# Add the reverse relationship on Business so the cascade config stays correct.
# Imported lazily to avoid a circular import at module load time.
def _register_business_relationship() -> None:
    from app.models.business import Business

    if not hasattr(Business, "data_sources"):
        Business.data_sources = relationship(  # type: ignore[attr-defined]
            "DataSource",
            back_populates="business",
            cascade="all, delete-orphan",
        )


_register_business_relationship()


__all__ = [
    "DataSource",
    "SyncRun",
    "SOURCE_TYPES",
    "SCHEDULES",
    "SYNC_STATUSES",
    "SOURCE_TYPE_FILE",
    "SOURCE_TYPE_SQL",
    "SCHEDULE_MANUAL",
    "SCHEDULE_HOURLY",
    "SCHEDULE_DAILY",
    "STATUS_NEVER_RUN",
    "STATUS_OK",
    "STATUS_PARTIAL",
    "STATUS_FAILED",
]


# Sanity-check constants used by routers/services. Keeping them as a single
# source of truth prevents accidental drift in documentation.

def _typing_only(d: dict[str, Any]) -> dict[str, Any]:
    return d


__typed__: dict[str, Any] = _typing_only({})
