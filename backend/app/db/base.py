"""SQLAlchemy declarative base + shared mixins."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid_str() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    """Common SQLAlchemy declarative base."""


class UUIDPrimaryKeyMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = ["Base", "UUIDPrimaryKeyMixin", "TimestampMixin"]


def coerce_uuid(value: str | UUID) -> str:
    return str(value) if isinstance(value, UUID) else str(value)


def to_dict(obj: Any) -> dict[str, Any]:
    """Helper for serialising SQLAlchemy models without leaking internal fields."""
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns}
