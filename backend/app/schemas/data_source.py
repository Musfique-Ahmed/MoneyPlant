"""Pydantic schemas for data sources + sync runs.

SECURITY: the :class:`DataSourceRead` schema DOES NOT include the
``secret_ref`` field. It is only accepted on :class:`DataSourceCreate`
and :class:`DataSourceUpdate`. The server resolves the env var name to
a connection URL internally and never returns either the name or the
URL to the client. ``/api/config/public`` does not list them either.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.data_source import (
    SCHEDULES,
    SOURCE_TYPES,
    SYNC_STATUSES,
)


class DataSourceConfig(BaseModel):
    """Non-secret configuration for a data source.

    The exact shape depends on the source ``type``:

    - ``file``: ``{"path": "inbox/sample.xlsx", "sheet_name": "Sheet1"}``.
      Path is validated against the configured allowed directory at write
      time (path-traversal + symlink-escape rejection).
    - ``sql``: ``{"table": "public.invoices", "schema_name": "public",
      "statement_timeout_seconds": 30, "row_limit": 50000}``.
    """

    # ``schema`` shadows ``BaseModel.schema`` (which Pydantic v2 no
    # longer uses) — keep the field but rename to ``schema_name`` on the
    # read path to avoid confusion in the API.
    model_config = ConfigDict(extra="forbid")

    # ``file`` config
    path: str | None = None
    sheet_name: str | None = None

    # ``sql`` config
    table: str | None = None
    schema_name: str | None = Field(default=None, alias="schema")
    statement_timeout_seconds: int = Field(default=30, ge=1, le=300)
    row_limit: int = Field(default=50_000, ge=1, le=1_000_000)

    @field_validator("path", "sheet_name", "table", "schema_name")
    @classmethod
    def _trim_and_bound(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) > 500:
            raise ValueError("value_too_long: max 500 chars")
        return v or None


class DataSourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_id: str = Field(min_length=1, max_length=36)
    type: str
    name: str = Field(min_length=1, max_length=200)
    config: DataSourceConfig
    column_mapping: dict[str, str] = Field(default_factory=dict)
    incremental_key: str | None = Field(default=None, max_length=64)
    schedule: str = "daily"
    enabled: bool = True
    # secret_ref is accepted here for SVC sources. The server stores it
    # as-is (env var name) and uses it to resolve the connection URL.
    secret_ref: str | None = Field(default=None, max_length=128)

    @field_validator("type")
    @classmethod
    def _type_valid(cls, v: str) -> str:
        if v not in SOURCE_TYPES:
            raise ValueError(f"type must be one of {SOURCE_TYPES}")
        return v

    @field_validator("schedule")
    @classmethod
    def _schedule_valid(cls, v: str) -> str:
        if v not in SCHEDULES:
            raise ValueError(f"schedule must be one of {SCHEDULES}")
        return v


class DataSourceUpdate(BaseModel):
    """PATCH endpoint payload. All fields optional."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    config: DataSourceConfig | None = None
    column_mapping: dict[str, str] | None = None
    incremental_key: str | None = Field(default=None, max_length=64)
    schedule: str | None = None
    enabled: bool | None = None
    secret_ref: str | None = Field(default=None, max_length=128)

    @field_validator("schedule")
    @classmethod
    def _schedule_valid(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in SCHEDULES:
            raise ValueError(f"schedule must be one of {SCHEDULES}")
        return v


class DataSourceRead(BaseModel):
    """Server-visible read shape — ``secret_ref`` is intentionally absent."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    business_id: str
    type: str
    name: str
    config: dict[str, Any]
    column_mapping: dict[str, str]
    incremental_key: str | None
    incremental_value: str | None
    file_content_sha256: str | None
    schedule: str
    enabled: bool
    last_sync_at: datetime | None
    last_status: str
    last_error_summary: str | None
    created_at: datetime
    updated_at: datetime


class DataSourceTestResult(BaseModel):
    """Result of ``POST /sources/{id}/test``."""

    model_config = ConfigDict(extra="forbid")

    status: str  # "ok" | "failed"
    last_message: str | None = None
    sample_rows: list[str] = Field(default_factory=list)
    headers: list[str] = Field(default_factory=list)
    row_count_preview: int = 0


class SyncRunRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    source_id: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    rows_read: int
    rows_added: int
    rows_skipped_duplicate: int
    rows_rejected: int
    validation_issues: list[dict[str, Any]] = Field(default_factory=list)
    error_summary: str | None
    trigger: str


class SyncRunList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SyncRunRead]


__all__ = [
    "DataSourceConfig",
    "DataSourceCreate",
    "DataSourceUpdate",
    "DataSourceRead",
    "DataSourceTestResult",
    "SyncRunRead",
    "SyncRunList",
    "SOURCE_TYPES",
    "SCHEDULES",
    "SYNC_STATUSES",
]