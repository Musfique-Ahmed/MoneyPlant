"""Schemas for the import pipeline (preview, validate, commit, retrieve)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ImportRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row: int
    field: str
    severity: str  # "error" | "warning"
    message: str


class ImportPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str
    file_extension: str
    file_size_bytes: int
    encoding: str
    sheet_name: str | None = None
    headers: list[str] = Field(default_factory=list)
    sample_rows: list[dict[str, str]] = Field(default_factory=list)
    row_count: int = 0
    suggested_mapping: dict[str, str] = Field(default_factory=dict)
    issues: list[ImportRow] = Field(default_factory=list)


class ImportJobRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    business_id: str
    filename: str
    file_extension: str
    file_size_bytes: int
    encoding: str | None
    sheet_name: str | None
    column_mapping: dict[str, str]
    row_count_total: int
    row_count_imported: int
    row_count_rejected: int
    validation_issues: list[dict[str, Any]] = Field(default_factory=list)
    status: str
    created_at: datetime


__all__ = ["ImportRow", "ImportPreview", "ImportJobRead"]
