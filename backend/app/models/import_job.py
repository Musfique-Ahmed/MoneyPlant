"""Import job: one record per uploaded file."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin


class ImportJob(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "import_jobs"

    business_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(16), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    encoding: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    column_mapping: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    row_count_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_count_imported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_count_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_issues: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="committed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    business = relationship("Business", back_populates="imports")
